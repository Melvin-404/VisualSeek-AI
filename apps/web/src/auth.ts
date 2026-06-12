import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";
import Credentials from "next-auth/providers/credentials";

const isDev = process.env.NODE_ENV === "development";

/**
 * In development, use a simple Credentials provider so the app works
 * without a running Keycloak instance.  In production, Keycloak is the
 * sole identity provider.
 */
const providers = isDev
  ? [
      Credentials({
        name: "Dev Login",
        credentials: {
          email: { label: "Email", type: "email", placeholder: "admin@visionquery.local" },
        },
        async authorize(credentials) {
          // Auto-approve any login in dev
          return {
            id: "dev-user-001",
            name: "Dev Admin",
            email: (credentials?.email as string) || "admin@visionquery.local",
            role: "admin",
          };
        },
      }),
    ]
  : [
      Keycloak({
        clientId: process.env.AUTH_KEYCLOAK_ID!,
        clientSecret: process.env.AUTH_KEYCLOAK_SECRET!,
        issuer: process.env.AUTH_KEYCLOAK_ISSUER!,
      }),
    ];

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers,
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60, // 8 hours
  },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    authorized({ auth: session, request: { nextUrl } }) {
      const isLoggedIn = !!session?.user;
      const isProtected =
        nextUrl.pathname.startsWith("/cameras") ||
        nextUrl.pathname.startsWith("/search") ||
        nextUrl.pathname.startsWith("/alerts") ||
        nextUrl.pathname.startsWith("/analytics");

      if (isProtected && !isLoggedIn) {
        // In dev, allow all routes without login
        if (isDev) return true;
        return false; // redirects to signIn page
      }
      return true;
    },
    jwt({ token, user, account, profile }) {
      // Credentials provider passes the user object directly
      if (user) {
        token.role = (user as Record<string, unknown>).role as string || "viewer";
      }
      // Keycloak path
      if (account && account.provider === "keycloak") {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.idToken = account.id_token;
        token.expiresAt = account.expires_at;
      }
      if (profile) {
        const realmAccess = (profile as Record<string, unknown>).realm_access as
          | Record<string, string[]>
          | undefined;
        if (realmAccess?.roles?.[0]) {
          token.role = realmAccess.roles[0];
        }
      }
      return token;
    },
    session({ session, token }) {
      if (token.accessToken) {
        session.accessToken = token.accessToken as string;
      }
      if (token.role) {
        session.user.role = token.role as string;
      }
      return session;
    },
  },
});
