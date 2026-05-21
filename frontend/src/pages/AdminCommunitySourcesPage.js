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
  Megaphone, Check, X, EyeOff, Trash2, RotateCcw, Loader2, ExternalLink, Clock, Mail,
} from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Admin moderation queue for community sources. Auth via ?token=... in
 * the URL (same pattern as /admin/reports + /admin/digest). Lets you:
 *   - Approve a pending submission (becomes publicly listed)
 *   - Reject a pending submission (stays in DB, public list ignores it)
 *   - Hide an approved source (manual takedown without delete — useful
 *     when you want to suspend without losing the record)
 *   - Restore (re-approve) a previously hidden / auto-hidden record
 *   - Delete permanently (one click, cascades to reports)
 */

const STATUS_OPTIONS = [
  { value: 'pending',  label: 'Pending'  },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'hidden',   label: 'Hidden'   },
];

const CATEGORY_LABEL = {
  subreddit: 'Subreddit',
  facebook_group: 'Facebook group',
  facebook_page: 'Facebook page',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  blog: 'Blog',
  newsletter: 'Newsletter',
  podcast: 'Podcast',
  other: 'Other',
};

export default function AdminCommunitySourcesPage() {
  usePageTitle('Admin · Community sources');
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [statusFilter, setStatusFilter] = useState('pending');
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState({}); // source_id -> note

  const fetchSources = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/community-sources`, {
        params: { token, status_filter: statusFilter },
      });
      setSources(res.data.items || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load community sources');
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => { fetchSources(); }, [fetchSources]);

  const reviewSource = async (source, status) => {
    try {
      await axios.post(
        `${API_URL}/api/admin/community-sources/${source.source_id}/review`,
        { status, admin_notes: notes[source.source_id] || null },
        { params: { token } },
      );
      toast.success(`Marked ${status}`);
      fetchSources();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Action failed');
    }
  };

  const deleteSource = async (source) => {
    if (!window.confirm(`Permanently delete "${source.name}"? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API_URL}/api/admin/community-sources/${source.source_id}`, {
        params: { token },
      });
      toast.success('Deleted');
      fetchSources();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  if (!token) {
    return (
      <div className="container mx-auto max-w-xl py-16 px-4">
        <h1 className="font-heading text-2xl font-bold mb-2">Admin · Community sources</h1>
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
            <Megaphone className="h-6 w-6 text-primary" />
            Community sources
          </h1>
          <p className="text-sm text-muted-foreground">
            Review and approve creator submissions for the public directory.
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
          <Button variant="outline" onClick={fetchSources} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Refresh'}
          </Button>
        </div>
      </div>

      {loading && sources.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : sources.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Megaphone className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-lg font-medium">No {statusFilter} sources</p>
            <p className="text-sm text-muted-foreground mt-1">Try a different filter.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {sources.map((s) => (
            <SourceAdminCard
              key={s.source_id}
              source={s}
              note={notes[s.source_id] || ''}
              onNoteChange={(v) => setNotes({ ...notes, [s.source_id]: v })}
              onReview={(status) => reviewSource(s, status)}
              onDelete={() => deleteSource(s)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceAdminCard({ source, note, onNoteChange, onReview, onDelete }) {
  const isPending = source.status === 'pending';
  const isApproved = source.status === 'approved';
  const isHidden = source.is_hidden;

  return (
    <Card className="dark:border-white/10">
      <CardContent className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary">{CATEGORY_LABEL[source.category] || source.category}</Badge>
            <Badge variant={isPending ? 'destructive' : isApproved ? 'default' : 'outline'} className="capitalize">
              {source.status}
            </Badge>
            {isHidden && (
              <Badge variant="outline" className="border-amber-500 text-amber-500">
                <EyeOff className="h-3 w-3 mr-1" /> auto-hidden
              </Badge>
            )}
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              submitted {formatDistanceToNow(new Date(source.created_at), { addSuffix: true })}
            </span>
          </div>
          <Badge variant="outline" className="font-mono text-xs">{source.source_id}</Badge>
        </div>

        {/* Name + description */}
        <h3 className="font-heading text-lg font-semibold mb-1">{source.name}</h3>
        {source.description && (
          <p className="text-sm text-muted-foreground mb-3 whitespace-pre-wrap">{source.description}</p>
        )}

        {/* Coverage tags */}
        {source.coverage_tags?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {source.coverage_tags.map((tag, idx) => (
              <Badge key={idx} variant="secondary" className="text-xs">#{tag}</Badge>
            ))}
          </div>
        )}

        {/* Links */}
        {source.links?.length > 0 && (
          <div className="bg-muted/40 rounded-lg p-3 mb-3 space-y-1">
            <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Links</p>
            {source.links.map((lnk, idx) => (
              <a
                key={idx}
                href={ensureScheme(lnk.url)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm hover:text-primary transition-colors"
              >
                <ExternalLink className="h-3 w-3" />
                <span className="text-xs font-medium uppercase tracking-wide w-16">{lnk.platform}</span>
                <span className="break-all">{lnk.url}</span>
                {lnk.handle && <span className="text-xs text-muted-foreground">({lnk.handle})</span>}
              </a>
            ))}
          </div>
        )}

        {/* Submitter contact (admin-only) */}
        <div className="text-sm mb-3 flex items-center gap-2 flex-wrap">
          <span className="text-muted-foreground flex items-center gap-1">
            <Mail className="h-3 w-3" /> Submitter:
          </span>
          {source.submitter_name && <span className="font-medium">{source.submitter_name}</span>}
          <span className="text-xs text-muted-foreground">({source.submitter_email})</span>
        </div>

        {/* Notes textarea */}
        <Textarea
          placeholder="Admin notes (optional — saved with the action)"
          value={note}
          onChange={(e) => onNoteChange(e.target.value)}
          rows={2}
          className="mb-3 text-sm"
        />

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          {isPending && (
            <>
              <Button size="sm" onClick={() => onReview('approved')} data-testid={`approve-${source.source_id}`}>
                <Check className="h-4 w-4 mr-1" /> Approve
              </Button>
              <Button variant="outline" size="sm" onClick={() => onReview('rejected')}>
                <X className="h-4 w-4 mr-1" /> Reject
              </Button>
            </>
          )}
          {isApproved && !isHidden && (
            <Button variant="outline" size="sm" onClick={() => onReview('hidden')}>
              <EyeOff className="h-4 w-4 mr-1" /> Hide
            </Button>
          )}
          {(source.status === 'hidden' || isHidden || source.status === 'rejected') && (
            <Button variant="outline" size="sm" onClick={() => onReview('approved')}>
              <RotateCcw className="h-4 w-4 mr-1" /> Restore + Approve
            </Button>
          )}
          <Button variant="destructive" size="sm" onClick={onDelete} data-testid={`delete-${source.source_id}`}>
            <Trash2 className="h-4 w-4 mr-1" /> Delete
          </Button>
        </div>

        {/* History */}
        {(source.reviewed_at || source.admin_notes) && (
          <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground space-y-1">
            {source.reviewed_at && (
              <p>Reviewed {format(new Date(source.reviewed_at), 'MMM d, yyyy HH:mm')}</p>
            )}
            {source.admin_notes && <p className="italic">"{source.admin_notes}"</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ensureScheme(url) {
  const trimmed = (url || '').trim();
  if (!trimmed) return '#';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}
