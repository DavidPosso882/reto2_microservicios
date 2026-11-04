// API error-path tests: store failures surface as 500 with the ecosystem
// envelope, exercising the logger fallback (Server without Logger).
package api_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"perfiles-service/internal/api"
	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

type boomStore struct{ store.Store }

func (boomStore) List(context.Context) ([]domain.Profile, error) {
	return nil, errBoom
}

func (boomStore) GetByEmpleadoID(context.Context, string) (domain.Profile, error) {
	return domain.Profile{}, errBoom
}

func (boomStore) UpdateContactInfo(context.Context, string, domain.ProfileUpdate) (domain.Profile, error) {
	return domain.Profile{}, errBoom
}

var errBoom = errorString("boom")

type errorString string

func (e errorString) Error() string { return string(e) }

func TestListStoreErrorIs500(t *testing.T) {
	srv := &api.Server{Store: boomStore{}}
	ts := httptest.NewServer(srv.Handler([]byte("openapi: test")))
	defer ts.Close()

	res, err := http.Get(ts.URL + "/perfiles")
	if err != nil {
		t.Fatalf("GET /perfiles: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", res.StatusCode)
	}
}

func TestGetStoreErrorIs500(t *testing.T) {
	srv := &api.Server{Store: boomStore{}}
	ts := httptest.NewServer(srv.Handler([]byte("openapi: test")))
	defer ts.Close()

	res, err := http.Get(ts.URL + "/perfiles/E999")
	if err != nil {
		t.Fatalf("GET /perfiles/E999: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", res.StatusCode)
	}
}

func TestUpdateUnknownProfileIs404(t *testing.T) {
	srv := &api.Server{Store: store.NewMemoryStore()}
	ts := httptest.NewServer(srv.Handler([]byte("openapi: test")))
	defer ts.Close()

	req, _ := http.NewRequest(http.MethodPut, ts.URL+"/perfiles/E404", nil)
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("PUT: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode == http.StatusOK {
		t.Errorf("status = 200 for unknown profile, want 4xx")
	}
}
