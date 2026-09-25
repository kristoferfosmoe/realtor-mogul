"use client";

import { useParams } from "next/navigation";

import { PropertyView } from "@/components/portfolio/PropertyView";

export default function PropertyPage() {
  const { id } = useParams<{ id: string }>();
  return <PropertyView key={id} id={Number(id)} />;
}
