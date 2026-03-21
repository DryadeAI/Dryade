// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  FileText,
  Search,
  Mic,
  Clock,
  User,
  MessageSquare,
  X,
  Volume2,
} from "lucide-react";

// Note interface matching audio plugin's useNotes.ts
interface Note {
  id: string;
  title: string;
  entries: Array<{
    id: string;
    text: string;
    speaker: string;
    timestamp: number;
    isPartial?: boolean;
  }>;
  createdAt: number;
  updatedAt: number;
  duration: number;
  speakerCount: number;
  hasAudio?: boolean;
  audioUrl?: string;
  summary?: string;
}

const STORAGE_KEY = "dryade-audio-notes";

// Format duration in mm:ss
function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// Format relative time
function formatRelativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

// Load notes from localStorage (same key as audio plugin)
function loadNotes(): Note[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

// Note row component
function NoteRow({
  note,
  onClick,
}: {
  note: Note;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-3 py-2.5 rounded-lg transition-all duration-200",
        "hover:bg-sidebar-accent focus:bg-sidebar-accent",
        "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
        "group"
      )}
    >
      <div className="flex items-start gap-2.5">
        <FileText size={16} className="text-primary mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium truncate text-sidebar-foreground">
              {note.title}
            </span>
            {note.hasAudio && (
              <Volume2 size={12} className="text-primary shrink-0" />
            )}
          </div>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {note.entries.length > 0
              ? note.entries[0].text.slice(0, 60) + (note.entries[0].text.length > 60 ? "..." : "")
              : "Empty note"}
          </p>
          <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {formatRelativeTime(note.createdAt)}
            </span>
            <span className="flex items-center gap-1">
              <MessageSquare size={10} />
              {note.entries.length}
            </span>
            <span className="flex items-center gap-1">
              <User size={10} />
              {note.speakerCount}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}

// Empty state
function EmptyState({ onRecord }: { onRecord: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-3">
        <FileText size={24} className="text-primary" />
      </div>
      <h3 className="text-sm font-medium mb-1">No notes yet</h3>
      <p className="text-xs text-muted-foreground mb-4 max-w-[180px]">
        Create your first audio note by recording a conversation.
      </p>
      <Button
        variant="default"
        size="sm"
        onClick={onRecord}
        className="flex items-center gap-2"
      >
        <Mic size={14} />
        Start Recording
      </Button>
    </div>
  );
}

// No search results
function NoResults({ query, onClear }: { query: string; onClear: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
      <Search size={24} className="text-muted-foreground mb-3" />
      <p className="text-sm text-muted-foreground mb-2">
        No notes match "{query}"
      </p>
      <Button variant="ghost" size="sm" onClick={onClear}>
        Clear search
      </Button>
    </div>
  );
}

export const NotesWidget = () => {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  // Load notes on mount and listen for storage changes
  useEffect(() => {
    const load = () => {
      const loaded = loadNotes();
      setNotes(loaded);
      setLoading(false);
    };

    load();

    // Listen for changes from audio plugin (same tab or other tabs)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        load();
      }
    };

    // Also poll periodically for same-tab changes (localStorage doesn't fire events in same tab)
    const interval = setInterval(load, 2000);

    window.addEventListener("storage", handleStorageChange);
    return () => {
      window.removeEventListener("storage", handleStorageChange);
      clearInterval(interval);
    };
  }, []);

  // Filter notes by search query
  const filteredNotes = useMemo(() => {
    if (!searchQuery.trim()) return notes;
    const q = searchQuery.toLowerCase();
    return notes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.entries.some((e) => e.text.toLowerCase().includes(q))
    );
  }, [notes, searchQuery]);

  // Navigate to audio plugin with note selected
  const handleNoteClick = useCallback(
    (noteId: string) => {
      navigate(`/workspace/plugins/audio?note=${noteId}`);
    },
    [navigate]
  );

  // Navigate to audio plugin recording view
  const handleRecord = useCallback(() => {
    navigate("/workspace/plugins/audio?action=record");
  }, [navigate]);

  const handleClearSearch = useCallback(() => {
    setSearchQuery("");
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <span className="text-sm text-muted-foreground">Loading...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search Bar */}
      {notes.length > 0 && (
        <div className="px-3 py-2 border-b border-sidebar-border">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search notes..."
              className="pl-8 pr-8 h-8 text-sm bg-sidebar-accent/50 border-sidebar-border"
            />
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Record Button */}
      <div className="px-3 py-2 border-b border-sidebar-border">
        <Button
          variant="default"
          size="sm"
          onClick={handleRecord}
          className="w-full flex items-center justify-center gap-2"
        >
          <Mic size={14} />
          New Recording
        </Button>
      </div>

      {/* Notes List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {notes.length === 0 ? (
          <EmptyState onRecord={handleRecord} />
        ) : filteredNotes.length === 0 ? (
          <NoResults query={searchQuery} onClear={handleClearSearch} />
        ) : (
          <div className="flex flex-col gap-1">
            {filteredNotes.map((note) => (
              <NoteRow
                key={note.id}
                note={note}
                onClick={() => handleNoteClick(note.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Stats Footer */}
      {notes.length > 0 && (
        <div className="px-3 py-2 border-t border-sidebar-border">
          <p className="text-[10px] text-muted-foreground text-center">
            {notes.length} note{notes.length !== 1 ? "s" : ""} •{" "}
            {formatDuration(notes.reduce((acc, n) => acc + n.duration, 0))} total
          </p>
        </div>
      )}
    </div>
  );
};

export default NotesWidget;
