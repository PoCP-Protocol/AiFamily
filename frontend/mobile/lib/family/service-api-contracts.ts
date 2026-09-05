/** Exact Mobile contracts for backend/domains/service/api. */

export type ServiceChannel = "VIDEO" | "TEXT" | "OFFLINE";

export interface ServiceOfferingDto {
  service_offering_id: string;
  service_offering_ref: string;
  version_no: number;
  title: string;
  provider_id: string;
  provider_display_name: string;
  provider_kind: string;
  channel_options: ServiceChannel[];
  open_slot_count: number;
}

export interface AvailabilitySlotDto {
  availability_slot_id: string;
  availability_slot_ref: string;
  service_offering_id: string;
  starts_at: string;
  ends_at: string;
  channel: ServiceChannel;
  status: "OPEN" | "RESERVED" | "CLOSED";
  capacity: number;
  remaining_capacity: number;
}

export interface SubmitServiceBookingBody {
  service_offering_id: string;
  availability_slot_id: string;
  booking_ref: string;
  source_page_id: "UI-21";
  subject_person_id: string;
  consent_ref: string;
}

export interface ServiceBookingReceipt {
  booking_request_id: string;
  booking_ref: string;
  status: "DRAFT" | "REQUESTED" | "CONFIRMED" | "CANCELLED" | "EXPIRED";
  service_offering_id: string;
  availability_slot_id: string;
  row_version: number;
  external_effect: false;
  environment: "DEV" | "TEST";
}

export interface ServiceBookingProjectionRow {
  booking_request_id: string;
  booking_ref: string;
  booking_status: "DRAFT" | "REQUESTED" | "CONFIRMED" | "CANCELLED" | "EXPIRED";
  service_offering_ref: string;
  availability_slot_ref: string;
  starts_at: string;
  ends_at: string;
  channel: ServiceChannel;
  booking_service_record_id: string | null;
  service_record_status: "PENDING" | "SCHEDULED" | "CANCELLED" | "COMPLETED" | null;
  service_quality_rating: string | null;
  environment: "DEV" | "TEST";
  source_system: "TEST_FIXTURE";
  external_effect: false;
  /** Mobile view alias derived from booking_status by the API client. */
  status: ServiceBookingProjectionRow["booking_status"];
}

export interface ServiceCustomerProjection {
  family_id: string;
  bookings: ServiceBookingProjectionRow[];
}

/** Scope and authority fields must always be derived by the server. */
export const FORBIDDEN_SERVICE_BODY_FIELDS = [
  "tenant_id",
  "family_id",
  "actor_person_id",
  "environment",
  "correlation_id",
  "idempotency_key",
  "decided_by",
] as const;
