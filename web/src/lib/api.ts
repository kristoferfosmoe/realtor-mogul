import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type Financing = Required<Schemas["Financing"]>;
export type Deal = Required<Omit<Schemas["Deal"], "financing">> & { financing: Financing | null };
export type Analysis = Schemas["Analysis"];
export type Metrics = Schemas["Metrics"];
export type YearRow = Schemas["YearRow"];
export type SensitivityGrid = Schemas["SensitivityGrid"];
export type DealStatus = NonNullable<Schemas["DealIn"]["status"]>;
export type SavedDeal = Omit<Schemas["DealOut"], "inputs" | "status"> & {
  inputs: Deal;
  status: DealStatus;
};
export type MetricKey = {
  [K in keyof Metrics]: Metrics[K] extends number | null | undefined ? K : never;
}[keyof Metrics];

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new ApiError(await errorMessage(res));
  return (res.status === 204 ? undefined : await res.json()) as T;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]) {
      const { loc, msg } = body.detail[0] as { loc: (string | number)[]; msg: string };
      return `${loc.filter((p) => p !== "body").join(".")}: ${msg}`;
    }
  } catch {
    // fall through to the status line
  }
  return `${res.status} ${res.statusText}`;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  health: () => request<{ status: string }>("/health"),
  template: () => request<Deal>("/analysis/template"),
  analyze: (deal: Deal, signal?: AbortSignal) =>
    request<Analysis>("/analysis", { method: "POST", body: json(deal), signal }),
  sensitivity: (
    body: {
      deal: Deal;
      x_field: string;
      x_values: number[];
      y_field: string;
      y_values: number[];
      metric: MetricKey;
    },
    signal?: AbortSignal,
  ) => request<SensitivityGrid>("/analysis/sensitivity", { method: "POST", body: json(body), signal }),
  listDeals: () => request<SavedDeal[]>("/deals"),
  getDeal: (id: number) => request<SavedDeal>(`/deals/${id}`),
  createDeal: (body: { name: string; address: string | null; status: DealStatus; inputs: Deal }) =>
    request<SavedDeal>("/deals", { method: "POST", body: json(body) }),
  updateDeal: (
    id: number,
    body: { name: string; address: string | null; status: DealStatus; inputs: Deal },
  ) => request<SavedDeal>(`/deals/${id}`, { method: "PUT", body: json(body) }),
  deleteDeal: (id: number) => request<void>(`/deals/${id}`, { method: "DELETE" }),
};
