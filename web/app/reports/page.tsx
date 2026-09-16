"use client";
/**
 * Doctor report queue. Verified doctors only — enforced by the API, reflected by Guard.
 *
 * The table is deliberately a list of SCANS, not a list of patients. There is no name
 * column and no contact column because the API does not return those fields at all; see
 * the whitelist in src/api/reports.py.
 */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import { listReports, type ReportRow } from "@/lib/reports";
import AddPatient from "@/components/AddPatient";

function shortDate(iso: string) {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—"
    : d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function ReferralPill({ row }: { row: ReportRow }) {
  if (row.quality_status === "refused") return <span className="pill pill-warn">Ungradeable</span>;
  if (row.referable) return <span className="pill pill-refer">Referable</span>;
  if (row.referable === false) return <span className="pill pill-clear">No referral</span>;
  return <span className="pill">—</span>;
}

function StatusPill({ row }: { row: ReportRow }) {
  const on = row.review_status !== "pending";
  return <span className={`pill ${on ? "pill-done" : "pill-pending"}`}>{row.review_status_label}</span>;
}

function ReportsTable() {
  const [rows, setRows] = useState<ReportRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "referable">("all");

  useEffect(() => {
    listReports()
      .then((d) => setRows(d.reports))
      .catch((e) => setError(e.message));
  }, []);

  const shown = useMemo(() => {
    if (!rows) return [];
    if (filter === "pending") return rows.filter((r) => r.review_status === "pending");
    if (filter === "referable") return rows.filter((r) => r.referable);
    return rows;
  }, [rows, filter]);

  const counts = useMemo(() => ({
    all: rows?.length ?? 0,
    pending: rows?.filter((r) => r.review_status === "pending").length ?? 0,
    referable: rows?.filter((r) => r.referable).length ?? 0,
  }), [rows]);

  if (error) return <div className="err">{error}</div>;
  if (!rows) return <div className="card"><span className="spin" /> <span className="muted">Loading reports…</span></div>;

  return (
    <>
      <div className="factbar" style={{ marginTop: 0, marginBottom: 18 }}>
        <div className="fact"><span className="k">Reports</span><span className="v">{counts.all}</span></div>
        <div className="fact"><span className="k">Awaiting review</span><span className="v">{counts.pending}</span></div>
        <div className="fact"><span className="k">Referable</span><span className="v">{counts.referable}</span></div>
      </div>

      <div className="filterrow">
        {(["all", "pending", "referable"] as const).map((f) => (
          <button key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
            {f === "all" ? "All" : f === "pending" ? "Awaiting review" : "Referable"}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="card">
          <div className="eyebrow">Report queue</div>
          <p style={{ marginTop: 8 }}>
            Nothing here yet. Reports appear as images are screened.
          </p>
        </div>
      ) : (
        <div className="tblwrap">
          <table>
            <thead>
              <tr>
                <th>Scan ID</th><th>Date</th><th>Grade</th><th>Referral</th>
                <th>Confidence</th><th>Quality</th><th>Evidence</th><th>Review</th><th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.scan_id}>
                  <td className="mono">{r.scan_id}</td>
                  <td>{shortDate(r.created_at)}</td>
                  <td>
                    {r.ai_grade === null ? <span className="muted">—</span>
                      : <><strong>Grade {r.ai_grade}</strong>{" "}
                        <span className="muted" style={{ fontSize: ".78rem" }}>{r.ai_label}</span></>}
                  </td>
                  <td><ReferralPill row={r} /></td>
                  <td className="num">{r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : "—"}</td>
                  <td>
                    {r.quality_status === "pass"
                      ? <span className="muted">Pass</span>
                      : <span style={{ color: "var(--gold)" }}>Refused</span>}
                  </td>
                  <td>{r.explanation_available
                    ? <span className="muted">Grad-CAM</span>
                    : <span className="muted" style={{ opacity: .6 }}>—</span>}</td>
                  <td><StatusPill row={r} /></td>
                  <td><Link href={`/reports/${r.scan_id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="muted" style={{ fontSize: ".8rem", marginTop: 14 }}>
        Reports are identified by internal scan id. No patient name, mobile number or
        contact detail is stored in or served from this view.
      </p>
    </>
  );
}

export default function ReportsPage() {
  return (
    <Guard requireDoctor>
      <Shell>
        <h2 style={{ fontFamily: "var(--f-display)", fontWeight: 500, marginTop: 0 }}>
          Screening reports
        </h2>
        <p className="muted" style={{ marginTop: -6, marginBottom: 18 }}>
          The screenings of patients who have shared their record with you, anonymised
          for clinical review. A verified doctor account does not by itself open anybody
          else&rsquo;s results.
        </p>
        {/* How a doctor reaches a patient they have never met. */}
        <AddPatient onAdded={() => window.location.reload()} />
        <div style={{ height: 16 }} />
        <ReportsTable />
      </Shell>
    </Guard>
  );
}
