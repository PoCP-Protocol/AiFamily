const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

const config = getDefaultConfig(__dirname);
config.resolver.blockList = [
  /node_modules[\\/]\.pnpm[\\/]@testing-library\+user-event_[^\\/]+[\\/]node_modules[\\/]@testing-library[\\/]dom[\\/].*/,
];

module.exports = withNativeWind(config, {
  input: "./global.css",
  // iOS development needs an on-disk CSS module, while production exports
  // must use the virtual module to avoid a first-build Metro SHA-1 race.
  forceWriteFileSystem: process.env.NODE_ENV !== "production",
});
