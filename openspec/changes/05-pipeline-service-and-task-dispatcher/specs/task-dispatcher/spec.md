## Purpose

Defines an asynchronous task dispatching interface and Redis/ARQ implementation for enqueueing background ingestion jobs.

## ADDED Requirements

### Requirement: Abstract Task Dispatcher Protocol
The system SHALL provide an abstract protocol (`TaskDispatcher`) for dispatching background ingestion jobs without binding callers to a specific task queue implementation.

#### Scenario: Enqueue ingestion task via protocol
- **WHEN** an ingestion request is processed
- **THEN** the system dispatches the job asynchronously using the configured `TaskDispatcher` without blocking the caller.

### Requirement: ARQ Task Dispatcher Implementation
The system SHALL provide an ARQ-backed dispatcher that enqueues ingestion jobs onto Redis with `job_id`, `document_id`, and `url` parameters.

#### Scenario: Successful ARQ job enqueueing
- **WHEN** `enqueue_ingestion_job` is invoked with valid job ID, document ID, and URL
- **THEN** an ARQ job is created in Redis and ready for worker consumption.

### Requirement: Dispatch Error Handling
The system SHALL raise a domain exception (`DispatcherError`) if the underlying queue broker is unreachable or fails to enqueue the job.

#### Scenario: Broker connection failure
- **WHEN** Redis is unreachable during job dispatch
- **THEN** the dispatcher catches the connection error and raises a `DispatcherError` with descriptive details.
