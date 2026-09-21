// REST API tests with httptest + the in-memory store (no Postgres needed).
package api_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"perfiles-service/internal/api"
	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

func newServer(t *testing.T) (*httptest.Server, *store.MemoryStore) {
	t.Helper()
	s := store.NewMemoryStore()
	srv := &api.Server{Store: s}
	ts := httptest.NewServer(srv.Handler([]byte("openapi: test")))
	t.Cleanup(ts.Close)
	return ts, s
}

func doJSON(t *testing.T, method, url string, body any) (*http.Response, map[string]any) {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		raw, _ := json.Marshal(body)
		reader = bytes.NewReader(raw)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequest(method, url, reader)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, url, err)
	}
	defer res.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(res.Body).Decode(&out)
	return res, out
}

func seed(ts *httptest.Server, s *store.MemoryStore) {
	s.SeedForTests(domain.Profile{
		ID: "11111111-1111-1111-1111-111111111111", EmpleadoID: "E001",
		Nombre: "Juan", Apellido: "Pérez", Email: "juan.perez@empresa.com",
	})
}

// TestListPerfiles: GET /perfiles → 200 JSON array (empty at first, then
// with the seeded profile).
func TestListPerfiles(t *testing.T) {
	ts, s := newServer(t)
	res, err := http.Get(ts.URL + "/perfiles")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", res.StatusCode)
	}
	var list []map[string]any
	if err := json.NewDecoder(res.Body).Decode(&list); err != nil {
		t.Fatalf("GET /perfiles must return a JSON array: %v", err)
	}
	if len(list) != 0 {
		t.Errorf("expected empty list, got %v", list)
	}

	seed(ts, s)
	res2, err := http.Get(ts.URL + "/perfiles")
	if err != nil {
		t.Fatalf("get seeded: %v", err)
	}
	defer res2.Body.Close()
	var list2 []map[string]any
	_ = json.NewDecoder(res2.Body).Decode(&list2)
	if len(list2) != 1 || list2[0]["empleadoId"] != "E001" {
		t.Errorf("expected seeded profile in list, got %v", list2)
	}
}

// TestGetPerfil200: GET /perfiles/{empleadoId} found → 200 + camelCase JSON.
func TestGetPerfil200(t *testing.T) {
	ts, s := newServer(t)
	seed(ts, s)

	res, out := doJSON(t, "GET", ts.URL+"/perfiles/E001", nil)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", res.StatusCode)
	}
	for _, key := range []string{"id", "empleadoId", "nombre", "apellido", "email",
		"telefono", "direccion", "ciudad", "biografia", "archivado",
		"fechaCreacion", "fechaActualizacion"} {
		if _, ok := out[key]; !ok {
			t.Errorf("missing camelCase key %q in: %v", key, out)
		}
	}
	if out["empleadoId"] != "E001" || out["nombre"] != "Juan" {
		t.Errorf("unexpected payload: %v", out)
	}
}

// TestGetPerfil404: GET /perfiles/{empleadoId} unknown → 404 error envelope.
func TestGetPerfil404(t *testing.T) {
	ts, _ := newServer(t)
	res, out := doJSON(t, "GET", ts.URL+"/perfiles/E999", nil)
	if res.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", res.StatusCode)
	}
	if out["status"] != float64(404) || out["error"] == "" {
		t.Errorf("expected error envelope {status,error}, got: %v", out)
	}
}

// TestPutPerfil200: PUT updates contact fields and keeps identity.
func TestPutPerfil200(t *testing.T) {
	ts, s := newServer(t)
	seed(ts, s)

	body := map[string]any{
		// Identity fields present in the body must be IGNORED by the API.
		"nombre":    "CambiarIdentidad",
		"email":     "hacker@empresa.com",
		"telefono":  "+54 11 4444-5555",
		"ciudad":    "Buenos Aires",
		"biografia": "Desarrollador backend",
	}
	res, out := doJSON(t, "PUT", ts.URL+"/perfiles/E001", body)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d (%v)", res.StatusCode, out)
	}
	if out["telefono"] != "+54 11 4444-5555" || out["ciudad"] != "Buenos Aires" || out["biografia"] != "Desarrollador backend" {
		t.Errorf("contact fields not updated: %v", out)
	}
	if out["nombre"] != "Juan" || out["email"] != "juan.perez@empresa.com" {
		t.Errorf("identity fields must be ignored by PUT: %v", out)
	}
}

// TestPutPerfil404: PUT on unknown profile → 404 envelope.
func TestPutPerfil404(t *testing.T) {
	ts, _ := newServer(t)
	body := map[string]any{"ciudad": "Rosario"}
	res, out := doJSON(t, "PUT", ts.URL+"/perfiles/E999", body)
	if res.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", res.StatusCode)
	}
	if out["status"] != float64(404) {
		t.Errorf("expected envelope status 404, got: %v", out)
	}
}

// TestPutPerfilCuerpoInvalido: invalid JSON → 400 envelope.
func TestPutPerfilCuerpoInvalido(t *testing.T) {
	ts, _ := newServer(t)
	req, _ := http.NewRequest("PUT", ts.URL+"/perfiles/E001", bytes.NewReader([]byte("{invalid")))
	req.Header.Set("Content-Type", "application/json")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do: %v", err)
	}
	defer res.Body.Close()
	var out map[string]any
	_ = json.NewDecoder(res.Body).Decode(&out)
	if res.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", res.StatusCode)
	}
	if out["status"] != float64(400) || out["error"] == "" {
		t.Errorf("expected error envelope, got: %v", out)
	}
}

// TestHealth: GET /health → 200.
func TestHealth(t *testing.T) {
	ts, _ := newServer(t)
	res, out := doJSON(t, "GET", ts.URL+"/health", nil)
	if res.StatusCode != http.StatusOK || out["status"] != "ok" {
		t.Fatalf("health: %d %v", res.StatusCode, out)
	}
}

// TestOpenapiYaml: GET /openapi.yaml → 200 YAML.
func TestOpenapiYaml(t *testing.T) {
	ts, _ := newServer(t)
	res, err := http.Get(ts.URL + "/openapi.yaml")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", res.StatusCode)
	}
	if ct := res.Header.Get("Content-Type"); ct != "application/yaml" {
		t.Errorf("expected application/yaml, got %q", ct)
	}
}
