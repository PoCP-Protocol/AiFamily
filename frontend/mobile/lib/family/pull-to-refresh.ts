export interface FamilyRefreshTasks {
  refreshRemote(): Promise<void>;
  reloadLocal(): Promise<void>;
}

export type FamilyRefreshResult = Awaited<ReturnType<typeof runFamilyRefresh>>;

export async function runFamilyRefresh(tasks: FamilyRefreshTasks) {
  const results = await Promise.allSettled([tasks.refreshRemote(), tasks.reloadLocal()]);
  return {
    remote: results[0].status,
    local: results[1].status,
    completed: true as const,
  };
}

export function createFamilyRefreshRunner(tasks: FamilyRefreshTasks) {
  let inFlight: Promise<FamilyRefreshResult> | null = null;

  return () => {
    if (inFlight) return inFlight;
    inFlight = runFamilyRefresh(tasks).finally(() => {
      inFlight = null;
    });
    return inFlight;
  };
}
