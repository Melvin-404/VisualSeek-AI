"use client";

import React, { useState } from "react";
import { PDFDocument, rgb, StandardFonts } from "pdf-lib";
import { Download, Calendar, Mail, CheckCircle2 } from "lucide-react";

export function ReportGenerator() {
  const [generating, setGenerating] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [email, setEmail] = useState("");
  const [frequency, setFrequency] = useState("weekly");
  const [scheduledStatus, setScheduledStatus] = useState<string | null>(null);

  const generatePDF = async () => {
    setGenerating(true);
    try {
      // 1. Create PDF Document
      const pdfDoc = await PDFDocument.create();
      const page = pdfDoc.addPage([595.276, 841.890]); // A4 Size standard dimensions
      const { width, height } = page.getSize();
      
      const HelveticaBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
      const Helvetica = await pdfDoc.embedFont(StandardFonts.Helvetica);

      // 2. Draw Title Header
      page.drawText("VISUALSEEK AI - EXECUTIVE REPORT", {
        x: 40,
        y: height - 60,
        size: 18,
        font: HelveticaBold,
        color: rgb(0.22, 0.74, 0.97) // Cool Blue
      });

      // Subtitle
      page.drawText(`Generated: ${new Date().toLocaleDateString()} | Tenant: Executive Demo Org`, {
        x: 40,
        y: height - 85,
        size: 9,
        font: Helvetica,
        color: rgb(0.6, 0.6, 0.6)
      });

      // Horizontal Divider
      page.drawLine({
        start: { x: 40, y: height - 100 },
        end: { x: width - 40, y: height - 100 },
        thickness: 1,
        color: rgb(0.15, 0.15, 0.15)
      });

      // 3. Draw Executive KPI Summary Section
      page.drawText("1. Executive Summary KPIs", {
        x: 40,
        y: height - 130,
        size: 13,
        font: HelveticaBold,
        color: rgb(0.9, 0.9, 0.9)
      });

      const kpiTableY = height - 150;
      const kpis = [
        ["Active Cameras / Fleet", "8 / 10 active nodes"],
        ["Total Events Logged", "1,245 alerts/day average"],
        ["Semantic Queries Executed", "143 search terms"],
        ["Average Vector Latency", "45.2 milliseconds"],
        ["Fleet Uptime Ratio", "99.85% (Optimal)"]
      ];

      kpis.forEach((row, i) => {
        const yPos = kpiTableY - (i * 20);
        // Zebra striping backgrounds
        if (i % 2 === 0) {
          page.drawRectangle({
            x: 40,
            y: yPos - 5,
            width: width - 80,
            height: 18,
            color: rgb(0.08, 0.08, 0.08)
          });
        }
        page.drawText(row[0], { x: 50, y: yPos, size: 9, font: Helvetica, color: rgb(0.7, 0.7, 0.7) });
        page.drawText(row[1], { x: 280, y: yPos, size: 9, font: HelveticaBold, color: rgb(1.0, 1.0, 1.0) });
      });

      // 4. Draw Chart Placeholder representing de-identified statistics
      const chartSectionY = kpiTableY - 120;
      page.drawText("2. Object Classification Detections (90-Day Trends)", {
        x: 40,
        y: chartSectionY,
        size: 13,
        font: HelveticaBold,
        color: rgb(0.9, 0.9, 0.9)
      });

      // Draw a simulated trend graph chart using lines/rects
      const chartHeight = 100;
      const chartWidth = width - 80;
      const chartX = 40;
      const chartY = chartSectionY - 120;

      // Draw chart border box
      page.drawRectangle({
        x: chartX,
        y: chartY,
        width: chartWidth,
        height: chartHeight,
        color: rgb(0.05, 0.05, 0.05),
        borderWidth: 1,
        borderColor: rgb(0.15, 0.15, 0.15)
      });

      // Draw Gridlines
      for (let g = 1; g < 4; g++) {
        page.drawLine({
          start: { x: chartX, y: chartY + (g * 25) },
          end: { x: chartX + chartWidth, y: chartY + (g * 25) },
          thickness: 0.5,
          color: rgb(0.12, 0.12, 0.12)
        });
      }

      // Draw simulated line graph coordinates (De-identified counts)
      const pointsPeople = [20, 35, 55, 40, 75, 60, 85, 70];
      const pointsVehicles = [10, 25, 30, 20, 50, 45, 55, 48];
      const step = chartWidth / (pointsPeople.length - 1);

      for (let p = 0; p < pointsPeople.length - 1; p++) {
        // People trendline (Green)
        page.drawLine({
          start: { x: chartX + (p * step), y: chartY + pointsPeople[p] },
          end: { x: chartX + ((p + 1) * step), y: chartY + pointsPeople[p + 1] },
          thickness: 1.5,
          color: rgb(0.46, 0.725, 0.0)
        });
        // Vehicles trendline (Blue)
        page.drawLine({
          start: { x: chartX + (p * step), y: chartY + pointsVehicles[p] },
          end: { x: chartX + ((p + 1) * step), y: chartY + pointsVehicles[p + 1] },
          thickness: 1.5,
          color: rgb(0.23, 0.51, 0.96)
        });
      }

      // 5. Draw Compliance Statement footer
      page.drawText("GDPR/SOC2 Compliance: All track IDs anonymized. Personal Identifiable Information de-identified.", {
        x: 40,
        y: 40,
        size: 7,
        font: Helvetica,
        color: rgb(0.5, 0.5, 0.5)
      });

      // Save and Download
      const pdfBytes = await pdfDoc.save();
      const blob = new Blob([pdfBytes as any], { type: "application/pdf" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `VisualSeek_AnalyticsReport_${new Date().toISOString().slice(0, 10)}.pdf`;
      link.click();
    } catch (err) {
      console.error("Failed to generate PDF", err);
    } finally {
      setGenerating(false);
    }
  };

  const handleScheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const token = "mock-token";
      const res = await fetch("http://localhost:8000/api/v1/analytics/report/schedule", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          "X-Tenant-ID": "22222222-2222-2222-2222-222222222222"
        },
        body: JSON.stringify({ email, frequency })
      });
      if (res.ok) {
        setScheduledStatus("Report schedule saved successfully!");
        setEmail("");
      } else {
        setScheduledStatus("Error scheduling report. Please try again.");
      }
    } catch (err) {
      console.error("Failed to save schedule", err);
      setScheduledStatus("Connection error. Schedule failed.");
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-6 flex flex-col gap-6">
      <div>
        <h3 className="text-base font-bold text-foreground">Export & Scheduling</h3>
        <p className="text-xs text-muted-foreground">
          Download PDF reports or configure automated email delivery
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* PDF Download Panel */}
        <div className="rounded-lg border border-border/80 bg-muted/20 p-4 flex flex-col justify-between">
          <div>
            <h4 className="text-sm font-semibold text-foreground">Instant PDF Export</h4>
            <p className="text-xs text-muted-foreground mt-1">
              Compiles full 90-day activity trends, heatmaps, and camera statistics into an executive-grade PDF.
            </p>
          </div>
          <button
            onClick={generatePDF}
            disabled={generating}
            className="mt-6 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground transition-all hover:bg-primary/95 disabled:opacity-50 cursor-pointer"
          >
            <Download className="h-4 w-4" />
            {generating ? "Compiling PDF..." : "Export PDF Report"}
          </button>
        </div>

        {/* Schedule Panel */}
        <div className="rounded-lg border border-border/80 bg-muted/20 p-4 flex flex-col justify-between">
          <div>
            <h4 className="text-sm font-semibold text-foreground">Automated Reports</h4>
            <p className="text-xs text-muted-foreground mt-1">
              Configure scheduled reports to be sent directly to your executive team's mailbox.
            </p>
          </div>
          <button
            onClick={() => setScheduling(!scheduling)}
            className="mt-6 flex items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-xs font-semibold text-foreground transition-all hover:bg-muted cursor-pointer"
          >
            <Calendar className="h-4 w-4 text-muted-foreground" />
            Configure Schedule
          </button>
        </div>
      </div>

      {/* Scheduler Modal/Panel */}
      {scheduling && (
        <form
          onSubmit={handleScheduleSubmit}
          className="border-t border-border pt-4 animate-fade-in"
        >
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Schedule Report Configuration
          </h4>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <div>
              <label className="text-[10px] uppercase font-bold text-muted-foreground">
                Email Address
              </label>
              <div className="mt-1 relative flex items-center">
                <Mail className="absolute left-2.5 h-3.5 w-3.5 text-muted-foreground" />
                <input
                  type="email"
                  required
                  placeholder="executive@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-md border border-border bg-muted/50 py-1.5 pl-8 pr-3 text-xs text-foreground focus:outline-none focus:border-primary"
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] uppercase font-bold text-muted-foreground">
                Frequency
              </label>
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-muted/50 p-1.5 text-xs text-foreground focus:outline-none focus:border-primary"
              >
                <option value="daily">Daily Report</option>
                <option value="weekly">Weekly Report</option>
                <option value="monthly">Monthly Report</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="w-full rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 cursor-pointer"
              >
                Save Schedule
              </button>
            </div>
          </div>

          {scheduledStatus && (
            <div className="mt-3 flex items-center gap-2 text-xs text-primary font-medium animate-fade-in">
              <CheckCircle2 className="h-4 w-4" />
              <span>{scheduledStatus}</span>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
