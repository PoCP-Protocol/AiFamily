/* 可用性测试数据：仅保存在浏览器 localStorage，不代表真实服务供给、授权或预约。 */
export type MockConsentStatus = "ACTIVE" | "WITHDRAWN";
export type MockBookingStatus = "REQUESTED" | "CANCELLED";

export interface MockServiceOffering {
  id: string;
  title: string;
  expert: string;
  channel: string;
  duration: string;
  fit: string;
  boundary: string;
  image: string;
  slots: { id: string; label: string; date: string; period: string }[];
}

export interface MockFamilySubject {
  id: string;
  name: string;
  role: string;
  availability: "AVAILABLE" | "CONSENT_REQUIRED";
}

export interface MockConsentGrant {
  consentRef: string;
  subjectPersonId: string;
  status: MockConsentStatus;
  purpose: "SERVICE_MATCHING";
  scope: string[];
  grantedAt: string;
  withdrawnAt?: string;
}

export interface MockBookingRequest {
  bookingRequestId: string;
  bookingRef: string;
  serviceOfferingId: string;
  availabilitySlotId: string;
  subjectPersonId: string;
  needSummary: string;
  status: MockBookingStatus;
  consent: MockConsentGrant;
  createdAt: string;
  updatedAt: string;
}

export const mockOfferings: MockServiceOffering[] = [
  {
    id: "offering-communication",
    title: "亲子沟通支持会谈",
    expert: "家庭沟通顾问",
    channel: "在线视频",
    duration: "50 分钟",
    fit: "适合冲突后难以重新开启对话的家庭",
    boundary: "提供沟通支持，不做临床诊断或疗效承诺",
    image: "/manus-storage/aifamily-service-listening-v2_a2f69b9f.jpg",
    slots: [
      { id: "slot-com-01", label: "周三 19:30", date: "9 月 2 日", period: "19:30–20:20" },
      { id: "slot-com-02", label: "周六 10:00", date: "9 月 5 日", period: "10:00–10:50" },
      { id: "slot-com-03", label: "周日 15:00", date: "9 月 6 日", period: "15:00–15:50" },
    ],
  },
  {
    id: "offering-routine",
    title: "家庭节奏共同梳理",
    expert: "成长计划顾问",
    channel: "在线视频",
    duration: "40 分钟",
    fit: "适合学习、手机和作息约定反复失效的家庭",
    boundary: "协助整理行动方案，不替家庭作决定",
    image: "/manus-storage/aifamily-service-rhythm-v2_01baceed.jpg",
    slots: [
      { id: "slot-rhythm-01", label: "周四 20:00", date: "9 月 3 日", period: "20:00–20:40" },
      { id: "slot-rhythm-02", label: "周六 14:30", date: "9 月 5 日", period: "14:30–15:10" },
      { id: "slot-rhythm-03", label: "时间待沟通", date: "提交后联系", period: "不自动确认" },
    ],
  },
];

export const mockSubjects: MockFamilySubject[] = [
  { id: "person-xiaoyu", name: "小宇", role: "家庭成员 · 9 岁", availability: "AVAILABLE" },
  { id: "person-lin", name: "林女士", role: "家庭管理员", availability: "AVAILABLE" },
];

const storageKey = "aifamily-usability-test-booking-v1";

export function loadMockBooking(): MockBookingRequest | null {
  try {
    const raw = window.localStorage.getItem(storageKey);
    return raw ? JSON.parse(raw) as MockBookingRequest : null;
  } catch {
    return null;
  }
}

export function saveMockBooking(booking: MockBookingRequest | null) {
  if (booking) window.localStorage.setItem(storageKey, JSON.stringify(booking));
  else window.localStorage.removeItem(storageKey);
}

export function createMockConsent(subjectPersonId: string): MockConsentGrant {
  return {
    consentRef: `mock-consent-${Date.now()}`,
    subjectPersonId,
    status: "ACTIVE",
    purpose: "SERVICE_MATCHING",
    scope: ["服务对象", "时间偏好", "本次需求摘要"],
    grantedAt: new Date().toISOString(),
  };
}

export function createMockBooking(input: { offeringId: string; slotId: string; subjectPersonId: string; needSummary: string; consent: MockConsentGrant }): MockBookingRequest {
  const now = new Date().toISOString();
  return {
    bookingRequestId: `mock-booking-request-${Date.now()}`,
    bookingRef: `AF-TEST-${String(Date.now()).slice(-6)}`,
    serviceOfferingId: input.offeringId,
    availabilitySlotId: input.slotId,
    subjectPersonId: input.subjectPersonId,
    needSummary: input.needSummary,
    status: "REQUESTED",
    consent: input.consent,
    createdAt: now,
    updatedAt: now,
  };
}
