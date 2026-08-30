import { Stack } from "expo-router";

import { FamilyExperienceHub } from "@/components/family/family-experience-hub";

export default function FamilyHubRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <FamilyExperienceHub />
    </>
  );
}

