import Svg, {
  Circle,
  G,
  Line,
  Polygon,
  Text as SvgText,
} from "react-native-svg";
import { StyleSheet, Text, View } from "react-native";

import {
  assessmentDimensionCaption,
  type AssessmentDimensionProfile,
} from "@/lib/family/assessment-dimension-profile";

const SIZE = 238;
const CENTER = SIZE / 2;
const RADIUS = 78;
const RINGS = [0.25, 0.5, 0.75, 1];

function pointFor(index: number, radius: number) {
  const angle = -Math.PI / 2 + (index * (Math.PI * 2)) / 5;
  return {
    x: CENTER + Math.cos(angle) * radius,
    y: CENTER + Math.sin(angle) * radius,
  };
}

function pointsFor(
  profiles: readonly AssessmentDimensionProfile[],
  radiusFor: (profile: AssessmentDimensionProfile) => number,
) {
  return profiles
    .map((profile, index) => {
      const point = pointFor(index, radiusFor(profile));
      return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    })
    .join(" ");
}

function statusColor(tone: AssessmentDimensionProfile["statusTone"]) {
  return tone === "focus"
    ? "#D24D44"
    : tone === "watch"
      ? "#B06A13"
      : tone === "quiet"
        ? "#2D8A72"
        : "#8A9BAD";
}

export function AssessmentDimensionRadar({
  profiles,
}: {
  profiles: readonly AssessmentDimensionProfile[];
}) {
  const allExplored = profiles.every((profile) => profile.explored);
  const points = profiles.map((profile, index) =>
    profile.explored ? pointFor(index, RADIUS * profile.signalValue) : null,
  );
  const labelPoints = profiles.map((_, index) => pointFor(index, RADIUS + 27));

  return (
    <View
      accessible
      accessibilityLabel="五个观察方向的家庭画像"
      style={styles.card}
    >
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>家庭成长画像</Text>
          <Text style={styles.title}>五个方向，看见家庭的不同侧面</Text>
          <Text style={styles.caption}>{assessmentDimensionCaption(profiles)}</Text>
        </View>
        <View style={styles.legendDot} />
      </View>
      <Svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        {RINGS.map((ring) => (
          <Polygon
            key={ring}
            points={pointsFor(profiles, () => RADIUS * ring)}
            fill={ring === 1 ? "#F8FBFF" : "none"}
            stroke="#D9E7F5"
            strokeWidth={ring === 1 ? 1.2 : 1}
          />
        ))}
        {profiles.map((_, index) => {
          const outer = pointFor(index, RADIUS);
          return (
            <Line
              key={`axis-${index}`}
              x1={CENTER}
              y1={CENTER}
              x2={outer.x}
              y2={outer.y}
              stroke="#E2EBF4"
              strokeWidth={1}
            />
          );
        })}
        {allExplored ? (
          <Polygon
            points={pointsFor(profiles, (profile) => RADIUS * profile.signalValue)}
            fill="#5A9EF533"
            stroke="#3F8DEB"
            strokeWidth={2}
          />
        ) : null}
        <Circle
          cx={CENTER}
          cy={CENTER}
          r={22}
          fill="#FFFFFF"
          stroke="#D9E7F5"
          strokeWidth={1}
        />
        <SvgText
          x={CENTER}
          y={CENTER + 4}
          fill="#5F7388"
          fontSize="10"
          fontWeight="700"
          textAnchor="middle"
        >
          本次观察
        </SvgText>
        {profiles.map((profile, index) => {
          const point = points[index];
          const nextIndex = (index + 1) % profiles.length;
          const next = points[nextIndex];
          return next && point && !allExplored ? (
            <Line
              key={`partial-line-${profile.focusId}`}
              x1={point.x}
              y1={point.y}
              x2={next.x}
              y2={next.y}
              stroke="#3F8DEB"
              strokeWidth={2}
            />
          ) : null;
        })}
        {profiles.map((profile, index) => {
          const point = points[index] ?? pointFor(index, RADIUS * 0.16);
          const label = labelPoints[index];
          return (
            <G key={profile.focusId}>
              <Circle
                cx={point.x}
                cy={point.y}
                r={profile.explored ? 4.5 : 3.5}
                fill={profile.explored ? "#3F8DEB" : "#CBD8E5"}
                stroke="#FFFFFF"
                strokeWidth={2}
              />
              <SvgText
                x={label.x}
                y={label.y}
                fill={profile.explored ? "#29445F" : "#8A9BAD"}
                fontSize="11"
                fontWeight="700"
                textAnchor="middle"
              >
                {profile.title}
              </SvgText>
            </G>
          );
        })}
      </Svg>
      <Text style={styles.note}>
        这是一张家庭观察图，不是总分。每个轴只表示本次回答留下的线索，未回答的方向不会被猜测。
      </Text>
    </View>
  );
}

export function AssessmentDimensionList({
  profiles,
  activeFocus,
}: {
  profiles: readonly AssessmentDimensionProfile[];
  activeFocus?: string | null;
}) {
  return (
    <View style={styles.dimensionList}>
      {profiles.map((profile) => (
        <View
          key={profile.focusId}
          style={[
            styles.dimensionCard,
            profile.focusId === activeFocus && styles.activeDimensionCard,
          ]}
        >
          <View style={styles.dimensionTopline}>
            <Text style={styles.dimensionTitle}>{profile.title}</Text>
            <Text style={[styles.dimensionStatus, { color: statusColor(profile.statusTone) }]}>
              {profile.statusLabel}
            </Text>
          </View>
          <Text style={styles.dimensionDefinition}>{profile.operationalDefinition}</Text>
          <View style={styles.signalRow}>
            {profile.signals.map((signal) => (
              <Text key={signal} style={styles.signalChip}>{signal}</Text>
            ))}
          </View>
          <Text style={styles.supportLine}>可从这里开始：{profile.supportDirection}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 22,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#DFEAF4",
    padding: 16,
    gap: 8,
  },
  header: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  headerCopy: { flex: 1, gap: 3 },
  eyebrow: { color: "#2875D7", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  title: { color: "#17324D", fontSize: 18, lineHeight: 25, fontWeight: "900" },
  caption: { color: "#6F8498", fontSize: 12, lineHeight: 18 },
  legendDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: "#5A9EF5", marginTop: 5 },
  note: { color: "#71859A", fontSize: 11, lineHeight: 17 },
  dimensionList: { gap: 9 },
  dimensionCard: {
    borderRadius: 17,
    backgroundColor: "#F9FBFD",
    borderWidth: 1,
    borderColor: "#E4ECF3",
    padding: 13,
    gap: 6,
  },
  activeDimensionCard: { backgroundColor: "#F1F7FF", borderColor: "#9BC5F7" },
  dimensionTopline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  dimensionTitle: { color: "#1D3853", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  dimensionStatus: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  dimensionDefinition: { color: "#5F7388", fontSize: 12, lineHeight: 18 },
  signalRow: { flexDirection: "row", flexWrap: "wrap", gap: 5 },
  signalChip: { color: "#3978B9", backgroundColor: "#EAF3FF", borderRadius: 8, paddingHorizontal: 7, paddingVertical: 3, fontSize: 10, lineHeight: 14, fontWeight: "800" },
  supportLine: { color: "#526B82", fontSize: 12, lineHeight: 18, fontWeight: "700" },
});
