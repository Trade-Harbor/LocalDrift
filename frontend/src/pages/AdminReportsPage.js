import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import {
  Flag, Trash2, RotateCcw, CheckCircle2, X, Loader2, AlertCircle, Clock, MessageSquare,
} from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Admin moderation queue. Auth: ?token=ADMIN_TOKEN in the URL, same
 * pattern as /admin/digest. List defaults to pending; can switch to
 * historical filters.
 *
 * Each report card surfaces:
 *   - reporter identity + reason + free-text details
 *   - snapshot of the target content captured at report time
 *   - action buttons: Dismiss / Dismiss + Restore / Action + Delete
 *   - optional reviewer notes textarea (saved on action)
 *
 * Auto-hidden flag is shown when the target's hide field is set so the
 * admin knows it's already pulled from the public feed.
 */

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'dismissed', label: 'Dismissed' },
];

const REASON_LABEL = {
  spam: 'Spam',
  abuse: 'Harassment / abuse',
  inappropriate: 'Inappropriate',
  misinformation: 'Misinformation',
  other: 'Other',
};

const TARGET_LABEL = {
  post: 'Forum post',
  comment: 'Comment',
  event: 'Event',
  user: 'User',
  creator: 'Community source',
};

export default function AdminReportsPage() {
  usePageTitle('Admin · Reports');
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [statusFilter, setStatusFilter] = useState('pending');
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState({});  // report_id -> notes

  const fetchReports = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/reports`, {
        params: { token, status_filter: statusFilter },
      });
      setReports(res.data.items || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load reports');
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleAction = async (report, { status, delete_target = false, restore_target = false }) => {
    try {
      const res = await axios.post(
        `${API_URL}/api/admin/reports/${report.report_id}/review`,
        {
          status,
          delete_target,
          restore_target,
          notes: notes[report.report_id] || null,
        },
        { params: { token } }
      );
      const { deleted_target, restored_target } = res.data;
      let msg = `Report marked ${status}`;
      if (deleted_target) msg += ' · target deleted';
      if (restored_target) msg += ' · target restored';
      toast.success(msg);
      fetchReports();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Action failed');
    }
  };

  if (!token) {
    return (
      <div className="container mx-auto max-w-xl py-16 px-4">
        <h1 className="font-heading text-2xl font-bold mb-2">Admin · Reports</h1>
        <p className="text-muted-foreground">
          Append <code>?token=YOUR_ADMIN_TOKEN</code> to the URL to access this page.
        </p>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl py-8 px-4">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
            <Flag className="h-6 w-6 text-red-500" />
            Reports queue
          </h1>
          <p className="text-sm text-muted-foreground">
            Review flagged content. Auto-hidden items are already pulled from public feeds.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={fetchReports} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Refresh'}
          </Button>
        </div>
      </div>

      {loading && reports.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : reports.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-3" />
            <p className="text-lg font-medium">No {statusFilter} reports</p>
            <p className="text-sm text-muted-foreground mt-1">
              {statusFilter === 'pending' ? 'Everything is calm. Check back later.' : 'Try a different filter.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {reports.map((report) => {
            const snap = report.target_snapshot || {};
            const isPending = report.status === 'pending';
            return (
              <Card key={report.report_id} className="dark:border-white/10">
                <CardContent className="p-5">
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="secondary" className="capitalize">
                        {TARGET_LABEL[report.target_type] || report.target_type}
                      </Badge>
                      <Badge variant={isPending ? 'destructive' : 'outline'}>
                        {REASON_LABEL[report.reason] || report.reason}
                      </Badge>
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
                      </span>
                    </div>
                    <Badge variant="outline" className="font-mono text-xs">
                      {report.report_id}
                    </Badge>
                  </div>

                  {/* Reporter */}
                  <div className="text-sm mb-3 flex items-center gap-2 flex-wrap">
                    <span className="text-muted-foreground">Reported by</span>
                    <span className="font-medium">{report.reporter_name || 'Unknown'}</span>
                    {report.reporter_email && (
                      <span className="text-xs text-muted-foreground">({report.reporter_email})</span>
                    )}
                  </div>

                  {/* User-supplied details */}
                  {report.details && (
                    <div className="bg-muted/40 rounded-lg p-3 mb-3 text-sm">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Reporter notes</p>
                      <p className="whitespace-pre-wrap">{report.details}</p>
                    </div>
                  )}

                  {/* Target snapshot */}
                  <div className="bg-card border border-border rounded-lg p-3 mb-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1">
                      <MessageSquare className="h-3 w-3" />
                      Flagged content (snapshot)
                    </p>
                    {snap.title && <p className="font-semibold mb-1">{snap.title}</p>}
                    {(snap.content || snap.description) && (
                      <p className="text-sm whitespace-pre-wrap">
                        {snap.content || snap.description}
                      </p>
                    )}
                    {(snap.author_name || snap.organizer_name) && (
                      <p className="text-xs text-muted-foreground mt-2">
                        By {snap.author_name || snap.organizer_name}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-2 font-mono">
                      ID: {report.target_id}
                    </p>
                  </div>

                  {/* Action notes + buttons (only for pending) */}
                  {isPending ? (
                    <>
                      <Textarea
                        placeholder="Reviewer notes (optional, saved with the action)"
                        value={notes[report.report_id] || ''}
                        onChange={(e) => setNotes({ ...notes, [report.report_id]: e.target.value })}
                        rows={2}
                        className="mb-3 text-sm"
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleAction(report, { status: 'dismissed' })}
                        >
                          <X className="h-4 w-4 mr-1" />
                          Dismiss
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleAction(report, { status: 'dismissed', restore_target: true })}
                        >
                          <RotateCcw className="h-4 w-4 mr-1" />
                          Dismiss + Restore
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => {
                            if (window.confirm('Delete the flagged content? This cannot be undone.')) {
                              handleAction(report, { status: 'actioned', delete_target: true });
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          Action + Delete
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="text-sm flex items-center gap-2 flex-wrap">
                      <Badge variant="secondary" className="capitalize">{report.status}</Badge>
                      {report.deleted_target && (
                        <span className="text-xs text-red-500 flex items-center gap-1">
                          <Trash2 className="h-3 w-3" /> deleted
                        </span>
                      )}
                      {report.restored_target && (
                        <span className="text-xs text-emerald-500 flex items-center gap-1">
                          <RotateCcw className="h-3 w-3" /> restored
                        </span>
                      )}
                      {report.reviewer_notes && (
                        <span className="text-xs text-muted-foreground italic">— {report.reviewer_notes}</span>
                      )}
                      {report.reviewed_at && (
                        <span className="text-xs text-muted-foreground ml-auto">
                          reviewed {format(new Date(report.reviewed_at), 'MMM d, HH:mm')}
                        </span>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
