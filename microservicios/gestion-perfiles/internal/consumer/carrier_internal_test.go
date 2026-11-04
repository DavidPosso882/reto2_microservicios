// White-box carrier tests: the AMQP↔W3C header adapter. Internal package
// because amqpCarrier is unexported; exercised indirectly by Handle too.
package consumer

import (
	"testing"
)

func TestCarrierRoundTrip(t *testing.T) {
	c := amqpCarrier{}
	c.Set("traceparent", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
	if got := c.Get("traceparent"); got == "" {
		t.Error("Get after Set returned empty")
	}
	if got := c.Get("ausente"); got != "" {
		t.Errorf("Get missing = %q, want empty", got)
	}
	// Non-string values never panic; they read as empty.
	c["objeto"] = 42
	if got := c.Get("objeto"); got != "" {
		t.Errorf("Get non-string = %q, want empty", got)
	}
	keys := c.Keys()
	if len(keys) != 2 {
		t.Errorf("Keys len = %d, want 2 (traceparent + objeto)", len(keys))
	}
}
