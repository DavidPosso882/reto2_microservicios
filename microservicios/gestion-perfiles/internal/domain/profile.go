// Package domain holds the profile domain model and event envelope types
// defined in CATALOGO_EVENTOS.md (the normative contract of the ecosystem).
package domain

import "time"

// Profile is the aggregate persisted in the perfiles table.
// JSON is camelCase per the service API contract.
type Profile struct {
	ID                 string    `json:"id"`
	EmpleadoID         string    `json:"empleadoId"`
	Nombre             string    `json:"nombre"`
	Apellido           string    `json:"apellido"`
	Email              string    `json:"email"`
	Telefono           string    `json:"telefono"`
	Direccion          string    `json:"direccion"`
	Ciudad             string    `json:"ciudad"`
	Biografia          string    `json:"biografia"`
	Archivado          bool      `json:"archivado"`
	FechaCreacion      time.Time `json:"fechaCreacion"`
	FechaActualizacion time.Time `json:"fechaActualizacion"`
}

// ProfileUpdate carries the fields the REST API allows to update
// (telefono, direccion, ciudad, biografia). Identity fields are ignored.
type ProfileUpdate struct {
	Telefono  *string `json:"telefono"`
	Direccion *string `json:"direccion"`
	Ciudad    *string `json:"ciudad"`
	Biografia *string `json:"biografia"`
}

// Event is the common envelope for all ecosystem events
// (CATALOGO_EVENTOS.md, section 1).
type Event struct {
	ID         string    `json:"id"`
	Type       string    `json:"type"`
	Version    string    `json:"version"`
	OccurredAt string    `json:"occurredAt"`
	Producer   string    `json:"producer"`
	Data       EventData `json:"data"`
}

// EventData is the flat "foto completa" payload of empleado.* events
// (sections 3.1, 3.2, 3.3). All fields optional; consumers tolerate
// missing fields.
type EventData struct {
	ID       string `json:"id"`
	Nombre   string `json:"nombre"`
	Apellido string `json:"apellido"`
	Email    string `json:"email"`
	Estado   string `json:"estado"`
}
