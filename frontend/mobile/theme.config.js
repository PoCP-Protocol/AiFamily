/** @type {const} */
// Warm Education：橙色负责行动，蓝色负责信任，绿色负责成长状态。
// App 与 Web 共用此唯一色彩真相，页面不得自行创建近似品牌色。
const themeColors = {
  primary: { light: '#F28C45', dark: '#FFB178' },
  trust: { light: '#0078D4', dark: '#45A9F0' },
  growth: { light: '#16866D', dark: '#46C7A8' },
  background: { light: '#FFF9F3', dark: '#14110F' },
  surface: { light: '#FFFFFF', dark: '#241E1A' },
  foreground: { light: '#10213E', dark: '#F8F4EF' },
  muted: { light: '#64748B', dark: '#B8AEA5' },
  border: { light: '#E8DED3', dark: '#40362F' },
  success: { light: '#16866D', dark: '#46C7A8' },
  warning: { light: '#B87500', dark: '#F6C453' },
  error: { light: '#D9554F', dark: '#F58A82' },
};

module.exports = { themeColors };
