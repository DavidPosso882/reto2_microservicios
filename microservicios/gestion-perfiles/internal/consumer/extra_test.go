// Status tests: health reporting without a broker (Run/consumeOnce need a
// live broker and stay covered by the Docker verification flow, not unit).
package consumer_test

import (
	"testing"

	"perfiles-service/internal/consumer"
)

func TestBrokerStatusDownWhenNeverConnected(t *testing.T) {
	c := &consumer.Consumer{}
	if got := c.BrokerStatus(); got != "DOWN" {
		t.Errorf("BrokerStatus = %q, want DOWN", got)
	}
}
