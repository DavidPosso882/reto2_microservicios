// Package api implements the REST API of perfiles-service.
//
// Error envelope (ecosystem contract): {"status": <http code>, "error": "..."}.
package api

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"

	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

// Store is the subset of store.Store the REST handlers need (narrowed so
// tests can mock it without Postgres).
type Store interface {
	List(ctx context.Context) ([]domain.Profile, error)
	GetByEmpleadoID(ctx context.Context, empleadoID string) (domain.Profile, error)
	UpdateContactInfo(ctx context.Context, empleadoID string, u domain.ProfileUpdate) (domain.Profile, error)
}

// Server serves the REST API of perfiles-service.
type Server struct {
	Store Store
}

// swaggerUIHTML is a dependency-free docs page: SwaggerUI from CDN loading
// the sibling ./openapi.yaml with a relative URL (gateway-safe).
const swaggerUIHTML = `<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>perfiles-service - Swagger UI</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>window.onload=()=>{SwaggerUIBundle({url:"./openapi.yaml",dom_id:"#swagger-ui"})};</script>
</body></html>`

// Handler builds the HTTP mux: REST routes, health and OpenAPI spec.
func (s *Server) Handler(openapiYAML []byte) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /perfiles", s.handleList)
	mux.HandleFunc("GET /perfiles/{empleadoId}", s.handleGet)
	mux.HandleFunc("PUT /perfiles/{empleadoId}", s.handleUpdate)
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "perfiles-service"})
	})
	mux.HandleFunc("GET /openapi.yaml", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/yaml")
		_, _ = w.Write(openapiYAML)
	})
	// Swagger UI mínimo sin dependencias: CDN + spec relativa ./openapi.yaml.
	// Relativa a propósito: funciona directo (:8083/docs) y vía gateway
	// (:8080/perfiles/docs -> /docs upstream, ./openapi.yaml -> /perfiles/openapi.yaml).
	mux.HandleFunc("GET /docs", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(swaggerUIHTML))
	})
	// Misma página en /docs/ SIN redirect: un 302 con Location: /docs pierde
	// el prefijo /perfiles vía gateway y el navegador termina en 404.
	mux.HandleFunc("GET /docs/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(swaggerUIHTML))
	})
	return mux
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]any{"status": code, "error": msg})
}

func (s *Server) handleList(w http.ResponseWriter, r *http.Request) {
	perfiles, err := s.Store.List(r.Context())
	if err != nil {
		log.Printf("perfiles-api: list perfiles: %v", err)
		writeError(w, http.StatusInternalServerError, "Error interno al listar perfiles")
		return
	}
	writeJSON(w, http.StatusOK, perfiles)
}

func (s *Server) handleGet(w http.ResponseWriter, r *http.Request) {
	empleadoID := r.PathValue("empleadoId")
	perfil, err := s.Store.GetByEmpleadoID(r.Context(), empleadoID)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "El perfil del empleado '"+empleadoID+"' no existe")
		return
	}
	if err != nil {
		log.Printf("perfiles-api: get perfil %s: %v", empleadoID, err)
		writeError(w, http.StatusInternalServerError, "Error interno al obtener el perfil")
		return
	}
	writeJSON(w, http.StatusOK, perfil)
}

func (s *Server) handleUpdate(w http.ResponseWriter, r *http.Request) {
	empleadoID := r.PathValue("empleadoId")

	var u domain.ProfileUpdate
	if err := json.NewDecoder(r.Body).Decode(&u); err != nil {
		writeError(w, http.StatusBadRequest, "Cuerpo JSON inválido")
		return
	}

	perfil, err := s.Store.UpdateContactInfo(r.Context(), empleadoID, u)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "El perfil del empleado '"+empleadoID+"' no existe")
		return
	}
	if err != nil {
		log.Printf("perfiles-api: update perfil %s: %v", empleadoID, err)
		writeError(w, http.StatusInternalServerError, "Error interno al actualizar el perfil")
		return
	}
	writeJSON(w, http.StatusOK, perfil)
}
