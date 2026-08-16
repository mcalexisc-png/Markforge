"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Toaster } from "sonner";

export function LanGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  React.useEffect(() => {
    const onUnauthorized = () => {
      router.replace("/?locked=1");
    };
    window.addEventListener("markforge:unauthorized", onUnauthorized);
    return () => window.removeEventListener("markforge:unauthorized", onUnauthorized);
  }, [router]);

  return (
    <>
      {children}
      <Toaster position="bottom-center" richColors closeButton />
    </>
  );
}
