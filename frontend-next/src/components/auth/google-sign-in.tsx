"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

interface GoogleSignInProps {
  onSuccess: (credential: string) => void;
  disabled?: boolean;
}

interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleAccountsId {
  initialize: (options: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }) => void;

  renderButton: (
    parent: HTMLElement,
    options: {
      theme: "outline";
      size: "large";
      width: string;
      text: "signin_with";
    },
  ) => void;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: GoogleAccountsId;
      };
    };
  }
}

export function GoogleSignIn({
  onSuccess,
  disabled = false,
}: GoogleSignInProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);

  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (!loaded || !clientId || !containerRef.current) {
      return;
    }

    const google = window.google;

    if (!google) {
      return;
    }

    containerRef.current.innerHTML = "";

    google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => {
        if (response.credential) {
          onSuccess(response.credential);
        }
      },
    });

    google.accounts.id.renderButton(containerRef.current, {
      theme: "outline",
      size: "large",
      width: "100%",
      text: "signin_with",
    });
  }, [loaded, clientId, onSuccess]);

  if (!clientId) {
    return null;
  }

  return (
    <div className={disabled ? "pointer-events-none opacity-50" : ""}>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => setLoaded(true)}
      />

      <div ref={containerRef} className="flex min-h-11 justify-center" />
    </div>
  );
}
