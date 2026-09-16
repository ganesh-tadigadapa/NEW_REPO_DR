/** @type {import('next').NextConfig} */
// distDir is overridable so a production build can be verified without clobbering the
// .next directory a running `next dev` is using. Defaults to the standard location.
module.exports = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
