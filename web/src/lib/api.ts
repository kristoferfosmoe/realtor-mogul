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

export type SeriesStats = Schemas["SeriesStats"];
export type MarketSummary = Schemas["MarketSummary"];
export type MarketDetail = Schemas["MarketDetail"];
export type MarketSeries = Schemas["SeriesOut"];
export type Indicator = Schemas["Indicator"];
export type Sources = Schemas["SourcesOut"];
export type Point = Schemas["Point"];

export type Portfolio = Schemas["PortfolioOut"];
export type Holding = Schemas["Holding"];
export type PropertyDetail = Schemas["PropertyDetail"];
export type PropertyOut = Schemas["PropertyOut"];
export type PropertyIn = Schemas["PropertyIn"];
export type PropertyType = NonNullable<PropertyIn["property_type"]>;
export type LoanIn = Schemas["LoanIn"];
export type Performance = Schemas["Performance"];
export type MonthRow = Schemas["MonthRow"];
export type LeaseIn = Schemas["LeaseIn"];
export type Lease = Schemas["LeaseOut"];
export type Transaction = Schemas["TransactionOut"];
export type TransactionIn = Schemas["TransactionIn"];
export type Category = Schemas["CategoryOut"];
export type ImportResult = Schemas["ImportOut"];
export type ValuationIn = Schemas["ValuationIn"];

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
  markets: () => request<MarketSummary[]>("/markets"),
  market: (id: number) => request<MarketDetail>(`/markets/${id}`),
  indicators: () => request<Indicator[]>("/markets/indicators"),
  sources: () => request<Sources>("/markets/sources"),

  portfolio: () => request<Portfolio>("/portfolio"),
  categories: () => request<Category[]>("/portfolio/categories"),
  property: (id: number) => request<PropertyDetail>(`/portfolio/properties/${id}`),
  createProperty: (body: PropertyIn) =>
    request<PropertyDetail>("/portfolio/properties", { method: "POST", body: json(body) }),
  createFromDeal: (dealId: number, purchaseDate: string) =>
    request<PropertyDetail>(
      `/portfolio/properties/from-deal/${dealId}?purchase_date=${encodeURIComponent(purchaseDate)}`,
      { method: "POST" },
    ),
  updateProperty: (id: number, body: PropertyIn) =>
    request<PropertyDetail>(`/portfolio/properties/${id}`, { method: "PUT", body: json(body) }),
  deleteProperty: (id: number) =>
    request<void>(`/portfolio/properties/${id}`, { method: "DELETE" }),
  addLease: (propertyId: number, body: LeaseIn) =>
    request<Lease>(`/portfolio/properties/${propertyId}/leases`, { method: "POST", body: json(body) }),
  updateLease: (id: number, body: LeaseIn) =>
    request<Lease>(`/portfolio/leases/${id}`, { method: "PUT", body: json(body) }),
  deleteLease: (id: number) => request<void>(`/portfolio/leases/${id}`, { method: "DELETE" }),
  transactions: (propertyId: number) =>
    request<Transaction[]>(`/portfolio/properties/${propertyId}/transactions`),
  addTransaction: (propertyId: number, body: TransactionIn) =>
    request<Transaction>(`/portfolio/properties/${propertyId}/transactions`, {
      method: "POST",
      body: json(body),
    }),
  importTransactions: (propertyId: number, csv: string) =>
    request<ImportResult>(`/portfolio/properties/${propertyId}/transactions/import`, {
      method: "POST",
      body: json({ csv }),
    }),
  patchTransaction: (id: number, body: { category?: TransactionIn["category"]; description?: string }) =>
    request<Transaction>(`/portfolio/transactions/${id}`, { method: "PATCH", body: json(body) }),
  deleteTransaction: (id: number) =>
    request<void>(`/portfolio/transactions/${id}`, { method: "DELETE" }),
  addValuation: (propertyId: number, body: ValuationIn) =>
    request<unknown>(`/portfolio/properties/${propertyId}/valuations`, {
      method: "POST",
      body: json(body),
    }),
  deleteValuation: (id: number) =>
    request<void>(`/portfolio/valuations/${id}`, { method: "DELETE" }),
};
