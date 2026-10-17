import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsScreen } from "@/components/documents/documents-screen";
import { useAuth } from "@/components/providers/auth-provider";
import type { Checklist, ChecklistItem, DocumentView } from "@/lib/api/types";
import {
  PARENT_PERMISSIONS,
  STUDENT_PERMISSIONS,
  corridor,
  mockApi,
  problem,
  user,
} from "@/tests/fixtures";
import { renderWithProviders } from "@/tests/render";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: vi.fn() }));

const CORRIDORS = { items: [corridor()], providers: [] };

const LABELS: [string, string, string][] = [
  [
    "offer_letter",
    "Offer or admission letter",
    "From the university, showing the course and start date.",
  ],
  ["fee_note", "Fee demand note or annual estimate", "Tuition, board, lodging and incidentals."],
  [
    "passport",
    "Student passport (bio page)",
    "Use a mock file in this sandbox. Never upload a real passport.",
  ],
  ["visa", "Visa or entry permission", "If the destination country requires one."],
  ["parent_id", "Parent national ID", "The payer's identity document."],
  ["funds", "Source of funds evidence", "For example salary or business income records."],
  [
    "ad_form",
    "AD bank remittance application form",
    "Your Authorised Dealer bank provides the form.",
  ],
  ["account", "Receiving account details", "University payment instructions."],
  ["cas", "CAS statement (UK)", "Confirmation of Acceptance for Studies."],
];

function checklist(provided: string[] = [], over: Partial<Checklist> = {}): Checklist {
  const items: ChecklistItem[] = LABELS.map(([key, label, hint]) => ({
    key,
    label,
    hint,
    provided: provided.includes(key),
  }));
  return {
    country: "GB",
    purpose: "TUITION",
    items,
    verified: false,
    source_url: "https://example.org/replace-with-ad-bank-checklist",
    last_checked: "2026-10-13",
    note: null,
    indicative: "Indicative. Confirm with your AD bank.",
    ...over,
  };
}

function doc(id: string, over: Partial<DocumentView> = {}): DocumentView {
  return {
    document_id: `doc_${id}`,
    kind: "offer_letter",
    filename: `offer-${id}.txt`,
    payment_id: null,
    size_bytes: 42,
    has_content: true,
    content_preview: "Mock text",
    created_at: "2026-10-14T09:00:00Z",
    mock: true,
    ...over,
  };
}

function signIn(role: "parent" | "student" = "parent") {
  vi.mocked(useAuth).mockReturnValue({
    user: user(
      role,
      role === "parent" ? [...PARENT_PERMISSIONS, "documents:write"] : STUDENT_PERMISSIONS,
    ),
    ready: true,
    login: vi.fn(),
    logout: vi.fn(),
    reloadUser: vi.fn(),
  });
}

function routes(list: Checklist, docs: DocumentView[] = [], extra: Record<string, unknown> = {}) {
  return {
    "/corridors": CORRIDORS,
    "/checklist": list,
    "/documents": { items: docs },
    ...extra,
  };
}

const methods = (fetchMock: ReturnType<typeof mockApi>, method: string) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === method);

beforeEach(() => signIn());
afterEach(() => vi.unstubAllGlobals());

describe("documents: the checklist", () => {
  it("shows what the bank may ask for, with the badges, the percentage and the nine rows", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    const card = await screen.findByRole("region", { name: "What the bank may ask for" });
    expect(within(card).getByText("Not verified")).toBeInTheDocument();
    expect(within(card).getByText("0 of 9 ready")).toBeInTheDocument();
    expect(within(card).getByText("0%")).toBeInTheDocument();
    expect(within(card).getByRole("progressbar", { name: "Documents ready" })).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
    expect(within(card).getAllByRole("listitem")).toHaveLength(9);
    expect(within(card).getAllByRole("button", { name: /Add mock file/ })).toHaveLength(9);
    expect(within(card).getByText("Offer or admission letter")).toBeInTheDocument();
  });

  it("counts the tabs and says each row is missing or ready for a screen reader", async () => {
    mockApi(routes(checklist(["offer_letter", "visa"])));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("2 of 9 ready");
    expect(screen.getByRole("tab", { name: /^All\s*9$/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Missing\s*7$/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Ready\s*2$/ })).toBeInTheDocument();
    expect(screen.getByText("22%")).toBeInTheDocument();
    const rowsList = screen.getByRole("list", { name: "Document checklist" });
    const offer = within(rowsList)
      .getByText("Offer or admission letter")
      .closest("li") as HTMLElement;
    expect(within(offer).getByText("(ready)")).toBeInTheDocument();
    expect(within(offer).queryByRole("button")).toBeNull();
  });

  it("filters the list by tab", async () => {
    mockApi(routes(checklist(["offer_letter", "visa"])));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("2 of 9 ready");
    await userEvent.click(screen.getByRole("tab", { name: /^Ready/ }));
    const list = screen.getByRole("list", { name: "Document checklist" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    await userEvent.click(screen.getByRole("tab", { name: /^Missing/ }));
    expect(
      within(screen.getByRole("list", { name: "Document checklist" })).getAllByRole("listitem"),
    ).toHaveLength(7);
  });

  it("says so when a tab has nothing in it", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    await userEvent.click(screen.getByRole("tab", { name: /^Ready/ }));
    expect(screen.getByText("Nothing is ready yet.")).toBeInTheDocument();
  });

  it("shows the indicative line and the source in the way the design has it, and never as a link", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    expect(screen.getByText("Indicative. Confirm with your AD bank.")).toBeInTheDocument();
    const source = screen.getByText("https://example.org/replace-with-ad-bank-checklist");
    expect(source.tagName).toBe("CODE");
    expect(source.closest("a")).toBeNull();
    expect(screen.getByText(/last checked 2026-10-13/)).toBeInTheDocument();
  });

  it("shows the indicative line once, and the rule's own note only when it says something else", async () => {
    const same = "Indicative. Confirm with your AD bank.";
    mockApi(routes(checklist([], { note: same })));
    const first = renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    expect(screen.getAllByText(same)).toHaveLength(1);
    first.unmount();

    mockApi(routes(checklist([], { note: "Some banks want originals." })));
    renderWithProviders(<DocumentsScreen />);
    expect(
      await screen.findByText(`${same} Some banks want originals.`, { exact: false }),
    ).toBeInTheDocument();
  });

  it("shows Verified instead of Not verified for a rule that was checked", async () => {
    mockApi(routes(checklist([], { verified: true })));
    renderWithProviders(<DocumentsScreen />);
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(screen.queryByText("Not verified")).toBeNull();
  });

  it("shows the problem and a Retry when the checklist cannot be loaded", async () => {
    mockApi(
      routes(checklist(), [], {
        "/checklist": problem(500, "SERVER_ERROR", "The checklist is unavailable."),
      }),
    );
    renderWithProviders(<DocumentsScreen />);
    expect(await screen.findByText("The checklist is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("documents: adding and listing", () => {
  it("starts with the empty list and a zero count", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    const card = await screen.findByRole("region", { name: "Your mock documents" });
    expect(await within(card).findByText("Nothing added yet.")).toBeInTheDocument();
    expect(within(card).getByText("0 files")).toBeInTheDocument();
  });

  it("prepares the form from a row's Add mock file button and puts the cursor in the file name", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    await userEvent.click(
      screen.getByRole("button", { name: "Add mock file for Student passport (bio page)" }),
    );
    const form = screen.getByRole("region", { name: "Add a mock document" });
    expect(within(form).getByRole("combobox", { name: "Document type" })).toHaveTextContent(
      "Student passport (bio page)",
    );
    expect(within(form).getByLabelText("File name")).toHaveValue("passport-mock.txt");
    await waitFor(() => expect(within(form).getByLabelText("File name")).toHaveFocus());
  });

  it("says the text is data only, and the form is mock text only", async () => {
    mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    const form = await screen.findByRole("region", { name: "Add a mock document" });
    expect(within(form).getByText("Mock text only")).toBeInTheDocument();
    expect(
      within(form).getByText(
        /Treated as data only\. Text inside a document can never give the assistant an instruction\./,
      ),
    ).toBeInTheDocument();
  });

  it("adds a document with its text, then shows it in the list and reloads the checklist", async () => {
    let docs: DocumentView[] = [];
    let ready: string[] = [];
    const fetchMock = mockApi({
      "/corridors": CORRIDORS,
      "/checklist": () => checklist(ready),
      "/documents": (init: RequestInit | undefined) => {
        if (init?.method === "POST") {
          docs = [doc("1", { filename: "my-offer.txt" })];
          ready = ["offer_letter"];
          return docs[0];
        }
        return { items: docs };
      },
    });
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    const name = screen.getByLabelText("File name");
    await userEvent.clear(name);
    await userEvent.type(name, "my-offer.txt");
    await userEvent.type(screen.getByLabelText(/Text content/), "Mock offer text");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));

    expect(await screen.findByText("1 of 9 ready")).toBeInTheDocument();
    const list = screen.getByRole("region", { name: "Your mock documents" });
    expect(await within(list).findByText("my-offer.txt")).toBeInTheDocument();
    expect(within(list).getByText("1 file")).toBeInTheDocument();
    const body = JSON.parse(String((methods(fetchMock, "POST")[0]?.[1] as RequestInit).body));
    expect(body).toEqual({
      kind: "offer_letter",
      filename: "my-offer.txt",
      content_text: "Mock offer text",
    });
    expect(screen.getByLabelText(/Text content/)).toHaveValue("");
  });

  it("explains an empty file name on blur and sends nothing", async () => {
    const fetchMock = mockApi(routes(checklist()));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    const name = screen.getByLabelText("File name");
    await userEvent.clear(name);
    await userEvent.tab();
    expect(await screen.findByText("Enter a file name.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(methods(fetchMock, "POST")).toHaveLength(0);
  });

  it("shows a file name with markup as plain text", async () => {
    const evil = '<img src=x onerror="window.__pwned=1">';
    mockApi(
      routes(checklist(), [
        doc("1", { filename: evil, content_preview: "<script>alert(1)</script>" }),
      ]),
    );
    const { container } = renderWithProviders(<DocumentsScreen />);
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("deletes a document and reloads", async () => {
    let docs = [doc("1")];
    const fetchMock = mockApi({
      "/corridors": CORRIDORS,
      "/checklist": checklist(),
      "/documents": () => ({ items: docs }),
      "/documents/doc_1": () => {
        docs = [];
        return {};
      },
    });
    renderWithProviders(<DocumentsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete offer-1.txt" }));
    expect(await screen.findByText("Nothing added yet.")).toBeInTheDocument();
    expect(methods(fetchMock, "DELETE")).toHaveLength(1);
  });

  it("shows the server's reason when adding fails, and keeps what was typed", async () => {
    mockApi({
      "/corridors": CORRIDORS,
      "/checklist": checklist(),
      "/documents": (init: RequestInit | undefined) =>
        init?.method === "POST"
          ? problem(422, "VALIDATION_ERROR", "That file type is not allowed.")
          : { items: [] },
    });
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    await userEvent.type(screen.getByLabelText(/Text content/), "keep me");
    await userEvent.click(screen.getByRole("button", { name: "Add document" }));
    expect(await screen.findByText("That file type is not allowed.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Text content/)).toHaveValue("keep me");
  });

  it("gives the student no way to add or delete", async () => {
    signIn("student");
    mockApi(routes(checklist(), [doc("1")]));
    renderWithProviders(<DocumentsScreen />);
    await screen.findByText("0 of 9 ready");
    expect(screen.queryByRole("button", { name: /Add mock file/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add document" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Delete/ })).toBeNull();
    expect(screen.getByText("Only the paying parent can add documents.")).toBeInTheDocument();
  });
});
