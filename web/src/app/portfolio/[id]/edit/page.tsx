"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { PropertyForm } from "@/components/portfolio/PropertyForm";
import { api, type PropertyOut } from "@/lib/api";

export default function EditPropertyPage() {
  const { id } = useParams<{ id: string }>();
  const [prop, setProp] = useState<PropertyOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .property(Number(id))
      .then((d) => setProp(d.property))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [id]);

  if (error) return <div className="empty down">{error}</div>;
  if (!prop) return <div className="empty">LOADING…</div>;
  return <PropertyForm existing={prop} />;
}
