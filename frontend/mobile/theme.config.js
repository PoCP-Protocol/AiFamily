/** @type {const} */
// 色系与移动 UI 原始基线一致：极浅蓝灰底、克制白卡、深蓝文字和多彩功能强调色。App 与 Web 共用此令牌，改此处两端同步。
const themeColors = {
  primary: { light: '#2F7BF4', dark: '#60A5FA' },
  background: { light: '#F8FBFD', dark: '#0F1620' },
  surface: { light: '#FEFFFF', dark: '#1A2330' },
  foreground: { light: '#17233B', dark: '#E8EDF5' },
  muted: { light: '#62718B', dark: '#9DAAC0' },
  border: { light: '#DCE6F4', dark: '#2A3646' },
  success: { light: '#16866D', dark: '#5FCB8C' },
  warning: { light: '#F28C45', dark: '#FBB765' },
  error: { light: '#D9554F', dark: '#F58A82' },
};

module.exports = { themeColors };
