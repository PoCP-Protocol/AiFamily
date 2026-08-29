import { StyleSheet, Text, View } from "react-native";

import { IconSymbol } from "@/components/ui/icon-symbol";

// 用代码绘制的首页插画，替代位图截图；蓝色系设计语言，App 与 Web 共用。

type FamilyGroupProps = { scale?: number };

/** 一组家庭剪影（父/母/两个孩子），用于横幅与卡片右侧。 */
function FamilyGroup({ scale = 1 }: FamilyGroupProps) {
  const s = (value: number): number => value * scale;
  return (
    <View style={[styles.familyRow, { height: s(58) }]}>
      <Figure size={s(34)} skin="#F4C9A6" body="#3B82F6" head={s(15)} lift={s(6)} />
      <Figure size={s(44)} skin="#F6D3B0" body="#1D4ED8" head={s(19)} lift={s(0)} />
      <Figure size={s(26)} skin="#F4C9A6" body="#93C5FD" head={s(12)} lift={s(14)} />
      <Figure size={s(38)} skin="#F6D3B0" body="#60A5FA" head={s(16)} lift={s(3)} />
    </View>
  );
}

type FigureProps = { size: number; skin: string; body: string; head: number; lift: number };

/** 单个人物剪影：圆头 + 半圆身体。 */
function Figure({ size, skin, body, head, lift }: FigureProps): React.JSX.Element {
  return (
    <View style={{ width: size, alignItems: "center", justifyContent: "flex-end", marginBottom: lift }}>
      <View
        style={{
          width: head,
          height: head,
          borderRadius: head / 2,
          backgroundColor: skin,
          marginBottom: -head * 0.28,
          zIndex: 2,
        }}
      />
      <View
        style={{
          width: size,
          height: size * 0.9,
          borderTopLeftRadius: size * 0.55,
          borderTopRightRadius: size * 0.55,
          backgroundColor: body,
        }}
      />
    </View>
  );
}

/** 免费家庭测评横幅（自绘）。 */
export function AssessmentBannerArt(): React.JSX.Element {
  return (
    <View style={styles.banner}>
      <View style={styles.bannerLayerMid} />
      <View style={styles.bannerLayerLight} />
      <View style={styles.bannerBlobA} />
      <View style={styles.bannerBlobB} />
      <View style={styles.bannerContent}>
        <View style={styles.bannerText}>
          <Text numberOfLines={1} style={styles.bannerTitle}>免费家庭测评</Text>
          <Text numberOfLines={1} style={styles.bannerSubtitle}>3 分钟了解孩子成长状况</Text>
          <Text numberOfLines={1} style={styles.bannerSubtitle}>获取专属建议</Text>
          <View style={styles.bannerCta}>
            <Text style={styles.bannerCtaText}>立即测评</Text>
            <IconSymbol name="chevron.right" size={15} color="#1D4ED8" />
          </View>
        </View>
        <View style={styles.bannerArt}>
          <View style={styles.bannerSun} />
          <FamilyGroup scale={0.92} />
        </View>
      </View>
    </View>
  );
}

type RecommendationKind = "live" | "course" | "case";

type RecommendationArtProps = { kind: RecommendationKind };

const REC_ART: Record<RecommendationKind, {
  badge: string;
  badgeColor: string;
  base: string;
  glow: string;
  panel: string;
  skin: string;
  outfit: string;
  hair: string;
  icon: Parameters<typeof IconSymbol>[0]["name"];
}> = {
  live: { badge: "直播预告", badgeColor: "#E5544B", base: "#2B4C86", glow: "#5B8AD6", panel: "#1E3A6B", skin: "#F2C6A0", outfit: "#26364F", hair: "#2A2420", icon: "video.fill" },
  course: { badge: "精选课程", badgeColor: "#F59D34", base: "#0E7C8C", glow: "#3FD0D9", panel: "#0B5F6E", skin: "#F4CBA5", outfit: "#E7A24A", hair: "#3A2A1E", icon: "book.fill" },
  case: { badge: "真实案例", badgeColor: "#7C3AED", base: "#6D3AC0", glow: "#B58BF0", panel: "#57289C", skin: "#F2C6A0", outfit: "#EFE6FA", hair: "#33243F", icon: "person.2.fill" },
};

/** 推荐卡人物半身剪影，增加插画丰富度。 */
function PersonBust({ skin, outfit, hair }: { skin: string; outfit: string; hair: string }): React.JSX.Element {
  return (
    <View style={styles.bust}>
      <View style={styles.bustHairWrap}>
        <View style={[styles.bustHair, { backgroundColor: hair }]} />
        <View style={[styles.bustHead, { backgroundColor: skin }]} />
      </View>
      <View style={[styles.bustBody, { backgroundColor: outfit }]}>
        <View style={[styles.bustCollar, { backgroundColor: skin }]} />
      </View>
    </View>
  );
}

/** 推荐卡缩略图（自绘）：场景背景 + 人物 + 徽章 + 角标图标。 */
export function RecommendationArt({ kind }: RecommendationArtProps): React.JSX.Element {
  const art = REC_ART[kind];
  return (
    <View style={[styles.recArt, { backgroundColor: art.base }]}>
      <View style={[styles.recGlow, { backgroundColor: art.glow }]} />
      <View style={[styles.recGlowSmall, { backgroundColor: art.glow, opacity: 0.4 }]} />
      <View style={[styles.recPanel, { backgroundColor: art.panel }]} />
      <PersonBust skin={art.skin} outfit={art.outfit} hair={art.hair} />
      <View style={[styles.recBadge, { backgroundColor: art.badgeColor }]}>
        <Text style={styles.recBadgeText}>{art.badge}</Text>
      </View>
      <View style={[styles.recIconChip, { backgroundColor: `${art.glow}E6` }]}>
        <IconSymbol name={art.icon} size={15} color="#0B1930" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  familyRow: { flexDirection: "row", alignItems: "flex-end", gap: 2 },

  banner: {
    height: 116,
    borderRadius: 18,
    overflow: "hidden",
    backgroundColor: "#2563EB",
    justifyContent: "center",
  },
  bannerLayerMid: { ...StyleSheet.absoluteFillObject, backgroundColor: "#3B82F6", left: "38%", borderTopLeftRadius: 120, borderBottomLeftRadius: 120 },
  bannerLayerLight: { ...StyleSheet.absoluteFillObject, backgroundColor: "#60A5FA", left: "62%", borderTopLeftRadius: 120, borderBottomLeftRadius: 120, opacity: 0.85 },
  bannerBlobA: { position: "absolute", top: -20, right: 22, width: 90, height: 90, borderRadius: 45, backgroundColor: "#93C5FD", opacity: 0.45 },
  bannerBlobB: { position: "absolute", bottom: -30, right: 96, width: 70, height: 70, borderRadius: 35, backgroundColor: "#BFDBFE", opacity: 0.4 },
  bannerContent: { flex: 1, flexDirection: "row", alignItems: "center", paddingHorizontal: 16 },
  bannerText: { flex: 1, minWidth: 0 },
  bannerTitle: { color: "#FFFFFF", fontSize: 19, fontWeight: "900", letterSpacing: 0.3 },
  bannerSubtitle: { color: "#E0ECFF", fontSize: 12, lineHeight: 18, marginTop: 1 },
  bannerCta: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", marginTop: 10, backgroundColor: "#FFFFFF", paddingHorizontal: 13, paddingVertical: 6, borderRadius: 20, gap: 2 },
  bannerCtaText: { color: "#1D4ED8", fontSize: 12, fontWeight: "800" },
  bannerArt: { width: 124, height: "100%", alignItems: "center", justifyContent: "center" },
  bannerSun: { position: "absolute", top: 12, right: 10, width: 30, height: 30, borderRadius: 15, backgroundColor: "#FBBF24", opacity: 0.9 },

  recArt: { width: "100%", height: "100%", overflow: "hidden" },
  recGlow: { position: "absolute", top: -30, left: -20, width: 90, height: 90, borderRadius: 45, opacity: 0.5 },
  recGlowSmall: { position: "absolute", top: 30, right: -16, width: 54, height: 54, borderRadius: 27 },
  recPanel: { position: "absolute", left: 0, right: 0, bottom: 0, height: "46%", opacity: 0.55 },
  recBadge: { position: "absolute", top: 8, left: 8, paddingHorizontal: 7, paddingVertical: 3, borderRadius: 6, zIndex: 3 },
  recBadgeText: { color: "#FFFFFF", fontSize: 9, fontWeight: "800" },
  recIconChip: { position: "absolute", top: 8, right: 8, width: 26, height: 26, borderRadius: 13, alignItems: "center", justifyContent: "center", zIndex: 3 },

  bust: { position: "absolute", left: 0, right: 0, bottom: 0, alignItems: "center", zIndex: 2 },
  bustHairWrap: { alignItems: "center", zIndex: 2 },
  bustHair: { position: "absolute", top: -4, width: 44, height: 40, borderTopLeftRadius: 22, borderTopRightRadius: 22, borderBottomLeftRadius: 10, borderBottomRightRadius: 10 },
  bustHead: { width: 34, height: 34, borderRadius: 17, marginTop: 2 },
  bustBody: { width: 84, height: 46, borderTopLeftRadius: 42, borderTopRightRadius: 42, marginTop: -6, alignItems: "center" },
  bustCollar: { width: 16, height: 22, marginTop: 6, borderBottomLeftRadius: 8, borderBottomRightRadius: 8 },
});
