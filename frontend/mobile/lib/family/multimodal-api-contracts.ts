export type ExperienceMediaKind = "TEXT" | "VOICE" | "IMAGE" | "AUDIO" | "VIDEO" | "INTERACTIVE_CARD";
export type ExperienceMediaStatus = "NOT_REQUESTED" | "CONSENT_REQUIRED" | "UPLOADING" | "READY" | "UPLOAD_FAILED";

export interface ExperienceMediaAttachment {
  media_id: string;
  kind: ExperienceMediaKind;
  status: ExperienceMediaStatus;
  consent_ref: string;
  synthetic: true;
}

export interface MultimodalAdapter {
  requestConsent(kind: ExperienceMediaKind): Promise<{ consent_ref: string }>;
  upload(input: { kind: ExperienceMediaKind; uri: string; consent_ref: string }): Promise<ExperienceMediaAttachment>;
}

export function createSyntheticMultimodalAdapter(): MultimodalAdapter {
  let sequence = 0;
  return {
    async requestConsent(kind) {
      return { consent_ref: `synthetic-consent-${kind.toLowerCase()}` };
    },
    async upload(input) {
      if (!input.uri.trim() || !input.consent_ref.trim()) throw new Error("synthetic_media_input_required");
      sequence += 1;
      return {
        media_id: `synthetic-media-${sequence}`,
        kind: input.kind,
        status: "READY",
        consent_ref: input.consent_ref,
        synthetic: true,
      };
    },
  };
}
