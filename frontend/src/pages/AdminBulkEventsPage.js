import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/textarea';
import {
  Upload, FileJson, CheckCircle2, AlertCircle, Loader2, Eye, Send,
} from 'lucide-react';
import { toast } from 'sonner';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Admin: bulk-import events via JSON paste.
 *
 * Workflow:
 *   1. Admin gathers event info from anywhere (Instagram captions, venue
 *      websites, hand-typed notes, Claude chat output)
 *   2. Shapes the data into a JSON array matching the EventCreate-lite
 *      schema below
 *   3. Pastes into the textarea, clicks Validate first (dry-run, no DB
 *      writes) to make sure parsing is clean
 *   4. Clicks Import → events appear in the public events tab
 *
 * Auth: ?token=ADMIN_TOKEN in URL (same pattern as other admin pages).
 */

const TEMPLATE = `[
  {
    "title": "Example concert",
    "description": "Indie band X at this venue",
    "category": "concert",
    "start_date": "2026-06-14T19:00:00",
    "location_name": "Bourgie Nights",
    "address": "127 Princess St",
    "city": "Wilmington",
    "state": "NC",
    "external_url": "https://example.com/tickets",
    "organizer_name": "Bourgie Nights",
    "source": "instagram",
    "tags": ["indie", "live music"]
  },
  {
    "title": "Saturday farmers market",
    "category": "market",
    "start_date": "2026-06-07T08:00:00",
    "end_date": "2026-06-07T13:00:00",
    "location_name": "Riverfront Park",
    "city": "Wilmington",
    "state": "NC",
    "organizer_name": "City of Wilmington"
  }
]`;

export default function AdminBulkEventsPage() {
  usePageTitle('Admin · Bulk import');
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [jsonText, setJsonText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [parseError, setParseError] = useState('');

  if (!token) {
    return (
      <div className="container mx-auto max-w-xl py-16 px-4">
        <h1 className="font-heading text-2xl font-bold mb-2">Admin · Bulk import</h1>
        <p className="text-muted-foreground">
          Append <code>?token=YOUR_ADMIN_TOKEN</code> to the URL to access this page.
        </p>
      </div>
    );
  }

  const parsePayload = () => {
    setParseError('');
    let parsed;
    try {
      parsed = JSON.parse(jsonText);
    } catch (e) {
      setParseError(`JSON parse error: ${e.message}`);
      return null;
    }
    if (!Array.isArray(parsed)) {
      setParseError('Top-level value must be an array of events.');
      return null;
    }
    if (parsed.length === 0) {
      setParseError('Array is empty.');
      return null;
    }
    return parsed;
  };

  const submit = async (dryRun) => {
    const events = parsePayload();
    if (!events) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await axios.post(
        `${API_URL}/api/admin/events/bulk`,
        { events, dry_run: dryRun },
        { params: { token } },
      );
      setResult(res.data);
      const verb = dryRun ? 'Validated' : 'Imported';
      toast.success(`${verb} ${res.data.inserted} of ${res.data.attempted} events`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.[0]?.msg || 'Bulk import failed';
      toast.error(msg);
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  };

  const loadTemplate = () => {
    setJsonText(TEMPLATE);
    setParseError('');
    setResult(null);
  };

  return (
    <div className="container mx-auto max-w-4xl py-8 px-4">
      <div className="mb-6">
        <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
          <Upload className="h-6 w-6 text-primary" />
          Bulk event import
        </h1>
        <p className="text-sm text-muted-foreground">
          Paste a JSON array of events. Dry-run first to validate before writing to the database.
        </p>
      </div>

      {/* JSON editor */}
      <Card className="dark:border-white/10 mb-4">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <label className="text-sm font-medium flex items-center gap-2">
              <FileJson className="h-4 w-4" />
              Events JSON
            </label>
            <Button type="button" size="sm" variant="outline" onClick={loadTemplate}>
              Load template
            </Button>
          </div>

          <Textarea
            value={jsonText}
            onChange={(e) => { setJsonText(e.target.value); setParseError(''); }}
            placeholder="Paste your JSON array here..."
            rows={20}
            className="font-mono text-xs leading-relaxed"
            data-testid="bulk-events-json"
          />

          {parseError && (
            <p className="text-sm text-red-500 flex items-center gap-1">
              <AlertCircle className="h-4 w-4" /> {parseError}
            </p>
          )}

          <div className="flex flex-wrap gap-2 justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => submit(true)}
              disabled={submitting || !jsonText.trim()}
              data-testid="bulk-validate"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
              Validate (dry-run)
            </Button>
            <Button
              type="button"
              onClick={() => submit(false)}
              disabled={submitting || !jsonText.trim()}
              data-testid="bulk-import"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Send className="h-4 w-4 mr-1" />}
              Import all
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Result panel */}
      {result && (
        <Card className="dark:border-white/10 mb-4">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              {result.dry_run ? (
                <Badge variant="outline">Dry run — nothing written</Badge>
              ) : (
                <Badge className="bg-emerald-500">Imported</Badge>
              )}
              <Badge variant="secondary">{result.attempted} attempted</Badge>
              <Badge className="bg-emerald-500/80">
                <CheckCircle2 className="h-3 w-3 mr-1" /> {result.inserted} ok
              </Badge>
              {result.skipped > 0 && (
                <Badge variant="destructive">
                  <AlertCircle className="h-3 w-3 mr-1" /> {result.skipped} failed
                </Badge>
              )}
            </div>

            {result.errors?.length > 0 && (
              <div className="bg-muted/40 rounded-lg p-3 text-xs space-y-2 max-h-[300px] overflow-y-auto">
                <p className="font-medium text-foreground text-sm">Per-row errors</p>
                {result.errors.map((err, idx) => (
                  <div key={idx} className="border-l-2 border-red-500 pl-3">
                    <p className="font-medium">Row {err.index}: {err.title || '(no title)'}</p>
                    <p className="text-muted-foreground">{err.error}</p>
                  </div>
                ))}
              </div>
            )}

            {!result.dry_run && result.inserted > 0 && (
              <p className="text-xs text-muted-foreground mt-3">
                Events imported. They'll appear in the public events tab immediately.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Help */}
      <Card className="bg-muted/30 dark:border-white/10">
        <CardContent className="p-4 text-sm text-muted-foreground space-y-2">
          <p className="font-medium text-foreground">How to use this page</p>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Click <strong>Load template</strong> to see the schema.</li>
            <li>
              Required fields: <code>title</code>, <code>start_date</code> (ISO 8601, e.g.
              <code>"2026-06-14T19:00:00"</code>).
            </li>
            <li>
              Optional fields: <code>description</code>, <code>category</code>,
              <code>end_date</code>, <code>location_name</code>, <code>address</code>,
              <code>city</code> (defaults Wilmington), <code>state</code> (defaults NC),
              <code>image_url</code>, <code>external_url</code>, <code>tags</code>,
              <code>organizer_name</code>, <code>source</code>.
            </li>
            <li>
              Always click <strong>Validate (dry-run)</strong> first. It runs parsing
              + insertion in memory without writing — surfaces per-row errors so you
              can fix the JSON before the real import.
            </li>
            <li>
              Categories: <code>concert, parade, marathon, market, happy_hour,
              garage_sale, food_festival, community, sports, other</code>.
              Unrecognized categories default to "other" in the public listing.
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
