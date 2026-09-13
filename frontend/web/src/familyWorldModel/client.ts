// HTTP client for the Family World Model demo endpoints
// (backend/apps/family_api/family_world_model_routes.py). Independent of
// familyGrowth/client.ts — this talks to a different, unrelated backend flow.

export type Speaker = "mother" | "father" | "child" | "self";
export type EpistemicKind = "PERSPECTIVE" | "SELF_REPORT" | "OBSERVATION" | "OTHER_REPORT" | "HYPOTHESIS";

export type StatementInput = {
  speaker: Speaker;
  epistemic_kind: "PERSPECTIVE" | "SELF_REPORT" | "OBSERVATION" | "OTHER_REPORT";
  predicate: string;
  text: string;
  subject_ids: string[];
};

export type WorldStateAtom = {
  atom_id: string;
  subject_ids: string[];
  epistemic_kind: EpistemicKind;
  predicate: string;
  value_ref: string;
  asserted_by: string;
  attributed_actor_type: string;
  provenance: string;
  recorded_at: string;
  support_level: string | null;
  contradiction_level: string | null;
  uncertainty: string | null;
  evidence_refs: string[];
  source_refs: string[];
};

export type WorldStateConflict = {
  conflict_id: string;
  predicate: string;
  atom_ids: string[];
  conflict_type: string;
  status: string;
  detected_at: string;
  resolution_note?: string | null;
};

export type WorldStateUnknown = {
  unknown_id: string;
  subject_ids: string[];
  question: string;
  why_it_matters: string;
  target_predicate: string;
  decision_impact: string;
  answerability: string;
  urgency: string;
  preferred_source: string;
  blocking_refs: string[];
  priority: string | number;
  status: string;
  resolution_refs?: string[];
  created_at: string | null;
  resolved_at?: string | null;
};

export type SubmitStatementsResponse = {
  family_id: string;
  atoms: WorldStateAtom[];
  conflicts: WorldStateConflict[];
};

export type CreateHypothesisResponse = {
  family_id: string;
  hypothesis: WorldStateAtom;
};

export type CreateUnknownResponse = {
  family_id: string;
  unknown: WorldStateUnknown | null;
};

export type ResolveUnknownResponse = {
  family_id: string;
  clarification_atom: WorldStateAtom;
  unknown: {
    unknown_id: string;
    status: string;
    resolution_refs: string[];
    resolved_at: string | null;
  };
};

export type BeliefState = {
  family_id: string;
  as_of: string;
  facts: WorldStateAtom[];
  observations: WorldStateAtom[];
  self_reports: WorldStateAtom[];
  other_reports: WorldStateAtom[];
  perspectives: WorldStateAtom[];
  hypotheses: WorldStateAtom[];
  effective_open_conflicts: WorldStateConflict[];
  effective_open_unknowns: WorldStateUnknown[];
};

export class FamilyWorldModelApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "家庭认知服务暂时不可用，请稍后重试。");
    this.name = "FamilyWorldModelApiError";
    this.status = status;
    this.detail = detail;
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type FamilyWorldModelClientOptions = {
  baseUrl?: string;
  fetchImpl?: FetchLike;
};

export class FamilyWorldModelApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(options: FamilyWorldModelClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async submitStatements(
    familyId: string,
    statements: StatementInput[],
  ): Promise<SubmitStatementsResponse> {
    return this.request<SubmitStatementsResponse>(
      `/families/${encodeURIComponent(familyId)}/world-model/statements`,
      { method: "POST", body: JSON.stringify({ statements }) },
    );
  }

  async createHypothesis(
    familyId: string,
    body: { subject_ids: string[]; target_predicate: string; evidence_atom_ids: string[] },
  ): Promise<CreateHypothesisResponse> {
    return this.request<CreateHypothesisResponse>(
      `/families/${encodeURIComponent(familyId)}/world-model/hypothesis`,
      { method: "POST", body: JSON.stringify(body) },
    );
  }

  async createUnknown(
    familyId: string,
    body: { subject_ids: string[]; hypothesis_atom_ids: string[]; allowed_target_predicates: string[] },
  ): Promise<CreateUnknownResponse> {
    return this.request<CreateUnknownResponse>(
      `/families/${encodeURIComponent(familyId)}/world-model/unknown`,
      { method: "POST", body: JSON.stringify(body) },
    );
  }

  async resolveUnknown(
    familyId: string,
    unknownId: string,
    clarification: StatementInput,
  ): Promise<ResolveUnknownResponse> {
    return this.request<ResolveUnknownResponse>(
      `/families/${encodeURIComponent(familyId)}/world-model/unknown/${encodeURIComponent(unknownId)}/resolve`,
      { method: "POST", body: JSON.stringify({ clarification }) },
    );
  }

  async getBeliefState(familyId: string, subjectIds: string[]): Promise<BeliefState> {
    const query = new URLSearchParams({ subject_ids: subjectIds.join(",") });
    return this.request<BeliefState>(
      `/families/${encodeURIComponent(familyId)}/world-model/belief-state?${query.toString()}`,
    );
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      const headers = new Headers(init.headers);
      headers.set("accept", "application/json");
      if (init.body) headers.set("content-type", "application/json");
      response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
    } catch {
      throw new FamilyWorldModelApiError(503, "服务暂时不可达。");
    }
    if (!response.ok) {
      let detail: unknown = response.statusText;
      try {
        const payload = (await response.json()) as { detail?: unknown };
        detail = payload.detail ?? detail;
      } catch {
        // Preserve the HTTP status when the server did not return JSON.
      }
      throw new FamilyWorldModelApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }
}
