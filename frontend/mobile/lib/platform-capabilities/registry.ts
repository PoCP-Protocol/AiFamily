import { CAPABILITY_IDS, type CapabilityById, type CapabilityDescriptor, type CapabilityId, type CapabilityResult, type CapabilityRuntimeContext, type CapabilityStatus, type PlatformCapabilityAdapters } from "./contracts";
import { capabilityMap } from "./adapters";

export interface CapabilityRegistry {
  readonly context: CapabilityRuntimeContext;
  readonly capabilities: CapabilityById;
  get<K extends CapabilityId>(id: K): CapabilityById[K];
  has(id: CapabilityId): boolean;
  descriptors(): readonly CapabilityDescriptor[];
  statusSnapshot(): Promise<{ [K in CapabilityId]: CapabilityResult<CapabilityStatus> }>;
}

export function createCapabilityRegistry(context: CapabilityRuntimeContext, adapters: PlatformCapabilityAdapters): CapabilityRegistry {
  const capabilities = capabilityMap(adapters);
  for (const id of CAPABILITY_IDS) {
    if (capabilities[id].descriptor.platform !== context.platform) throw new Error(`Capability adapter platform mismatch for ${id}`);
  }
  return {
    context,
    capabilities,
    get: (id) => capabilities[id],
    has: (id) => id in capabilities,
    descriptors: () => CAPABILITY_IDS.map((id) => capabilities[id].descriptor),
    statusSnapshot: async () => {
      const entries = await Promise.all(CAPABILITY_IDS.map(async (id) => [id, await capabilities[id].status()] as const));
      return Object.fromEntries(entries) as { [K in CapabilityId]: CapabilityResult<CapabilityStatus> };
    },
  };
}
