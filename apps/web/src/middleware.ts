import { auth } from "@/auth";

export default auth;

export const config = {
  matcher: [
    "/cameras/:path*",
    "/search/:path*",
    "/alerts/:path*",
    "/analytics/:path*",
  ],
};

