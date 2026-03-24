package producer

import (
	"fmt"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"go.uber.org/zap"
)

// AsyncProducer buffers events in a Go channel and flushes them to Kafka
// in micro-batches. The HTTP handler never waits for Kafka acknowledgement,
// keeping p99 latency at the pure network cost of the client round-trip.
type AsyncProducer struct {
	producer  *kafka.Producer
	topic     string
	queue     chan []byte
	batchSize int
	flushMs   int
	logger    *zap.Logger
}

// New creates and starts an AsyncProducer.
// batchSize: max number of messages per Kafka batch
// flushMs:   max milliseconds before flushing a partial batch
func New(brokers, topic string, queueSize, batchSize, flushMs int, logger *zap.Logger) (*AsyncProducer, error) {
	p, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers":            brokers,
		"queue.buffering.max.messages": 1_000_000,
		"queue.buffering.max.kbytes":   512_000, // 512 MB internal buffer
		"batch.num.messages":           batchSize,
		"linger.ms":                    flushMs,
		"compression.type":             "lz4",      // Compress at the Kafka level
		"acks":                         "1",        // Leader ack — fast but safe enough for analytics
		"delivery.timeout.ms":          30_000,
		"message.max.bytes":            1_048_576,  // 1 MB per Kafka message
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create kafka producer: %w", err)
	}

	ap := &AsyncProducer{
		producer:  p,
		topic:     topic,
		queue:     make(chan []byte, queueSize),
		batchSize: batchSize,
		flushMs:   flushMs,
		logger:    logger,
	}

	// Drain delivery reports — we log errors but never block the ingest path
	go ap.handleDeliveryReports()
	// Flush the in-process channel to Kafka in batches
	go ap.flushLoop()

	return ap, nil
}

// Enqueue places a raw byte payload onto the async queue.
// Returns false if the internal buffer is full (back-pressure signal).
func (ap *AsyncProducer) Enqueue(payload []byte) bool {
	select {
	case ap.queue <- payload:
		return true
	default:
		// Back-pressure: queue is full. Drop and log — data integrity is preserved in ODS
		ap.logger.Warn("Producer queue full, message dropped", zap.Int("queue_size", len(ap.queue)))
		return false
	}
}

// flushLoop reads from the internal channel and publishes to Kafka.
// It uses a ticker so partial batches are not held indefinitely.
func (ap *AsyncProducer) flushLoop() {
	ticker := time.NewTicker(time.Duration(ap.flushMs) * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case payload, ok := <-ap.queue:
			if !ok {
				return // Channel closed — shutdown
			}
			if err := ap.produce(payload); err != nil {
				ap.logger.Error("Kafka produce failed", zap.Error(err))
			}
		case <-ticker.C:
			// Flush any internal Kafka producer buffers every flushMs
			_ = ap.producer.Flush(ap.flushMs)
		}
	}
}

func (ap *AsyncProducer) produce(payload []byte) error {
	return ap.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &ap.topic, Partition: kafka.PartitionAny},
		Value:          payload,
	}, nil) // nil channel = fire-and-forget (delivery handled in handleDeliveryReports)
}

func (ap *AsyncProducer) handleDeliveryReports() {
	for e := range ap.producer.Events() {
		if m, ok := e.(*kafka.Message); ok {
			if m.TopicPartition.Error != nil {
				ap.logger.Error("Message delivery failed",
					zap.String("topic", *m.TopicPartition.Topic),
					zap.Error(m.TopicPartition.Error),
				)
			}
		}
	}
}

// Close gracefully drains the queue and shuts down the Kafka producer.
func (ap *AsyncProducer) Close() {
	close(ap.queue)
	ap.producer.Flush(5000)
	ap.producer.Close()
}
