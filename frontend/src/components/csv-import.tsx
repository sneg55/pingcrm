"use client";

import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { Upload, FileText, X, AlertCircle, CheckCircle } from "lucide-react";
import { client } from "@/lib/api-client";

type PreviewRow = Record<string, string>

type ImportResult = {
  created: number;
  errors: string[];
}

function parseCsvText(text: string): { headers: string[]; rows: PreviewRow[] } {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 0) return { headers: [], rows: [] };

  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  const rows = lines.slice(1, 6).map((line) => {
    const values = line.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
    const row: PreviewRow = {};
    headers.forEach((header, i) => {
      row[header] = values[i] ?? "";
    });
    return row;
  });

  return { headers, rows };
}

export function CsvImport() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ headers: string[]; rows: PreviewRow[] } | null>(
    null
  );
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const processFile = (f: File) => {
    setFile(f);
    setResult(null);
    setUploadError(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      setPreview(parseCsvText(text));
    };
    reader.readAsText(f);
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) processFile(f);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.type === "text/csv") {
      processFile(f);
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data, error } = await client.POST("/api/v1/contacts/import/csv", {
        body: formData as unknown as { file: string },
        bodySerializer: () => formData,
      });
      if (error || !data?.data) {
        setUploadError((error as { detail?: string })?.detail ?? "Import failed. Please try again.");
      } else {
        setResult(data.data as unknown as ImportResult);
        setFile(null);
        setPreview(null);
      }
    } catch {
      setUploadError("Import failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setUploadError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  if (result) {
    return (
      <div className="rounded-lg border border-gray-200 dark:border-stone-700 bg-white dark:bg-stone-900 p-4">
        <div className="flex items-start gap-3">
          <CheckCircle className="w-5 h-5 text-green-500 dark:text-emerald-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-stone-100">
              Import complete — {result.created} contact
              {result.created !== 1 ? "s" : ""} created
            </p>
            {result.errors.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-red-600 dark:text-red-400 font-medium mb-1">
                  {result.errors.length} row{result.errors.length !== 1 ? "s" : ""} had
                  errors:
                </p>
                <ul className="text-xs text-red-500 dark:text-red-400 space-y-0.5 max-h-24 overflow-y-auto">
                  {result.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <button onClick={handleReset} className="text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {!file ? (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
            isDragging
              ? "border-blue-400 dark:border-blue-600 bg-blue-50 dark:bg-blue-950"
              : "border-gray-300 dark:border-stone-600 hover:border-blue-300 dark:hover:border-blue-600 hover:bg-gray-50 dark:hover:bg-stone-800"
          }`}
        >
          <Upload className="w-8 h-8 text-gray-400 dark:text-stone-500 mx-auto mb-2" />
          <p className="text-sm font-medium text-gray-700 dark:text-stone-300">
            Drop a CSV file here, or click to browse
          </p>
          <p className="text-xs text-gray-400 dark:text-stone-500 mt-1">
            Supported columns: name, email, phone, company, title, tags
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      ) : (
        <div className="rounded-lg border border-gray-200 dark:border-stone-700 bg-white dark:bg-stone-900 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-500 dark:text-blue-400" />
              <span className="text-sm font-medium text-gray-800 dark:text-stone-100">{file.name}</span>
              <span className="text-xs text-gray-400 dark:text-stone-500">
                ({(file.size / 1024).toFixed(1)} KB)
              </span>
            </div>
            <button onClick={handleReset} className="text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300">
              <X className="w-4 h-4" />
            </button>
          </div>

          {preview && preview.rows.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-gray-500 dark:text-stone-400 mb-1.5">
                Preview (first {preview.rows.length} rows):
              </p>
              <div className="overflow-x-auto rounded-md border border-gray-100 dark:border-stone-700">
                <table className="text-xs w-full">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-stone-800">
                      {preview.headers.map((h) => (
                        <th
                          key={h}
                          className="px-2 py-1.5 text-left text-gray-600 dark:text-stone-300 font-medium border-b border-gray-100 dark:border-stone-700 whitespace-nowrap"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-b border-gray-50 dark:border-stone-800 last:border-0">
                        {preview.headers.map((h) => (
                          <td
                            key={h}
                            className="px-2 py-1.5 text-gray-700 dark:text-stone-300 max-w-[120px] truncate"
                          >
                            {row[h]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {uploadError && (
            <div className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-md px-3 py-2 mb-3">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              {uploadError}
            </div>
          )}

          <button
            onClick={() => void handleUpload()}
            disabled={isUploading}
            className="w-full py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isUploading ? "Importing..." : "Import contacts"}
          </button>
        </div>
      )}
    </div>
  );
}
