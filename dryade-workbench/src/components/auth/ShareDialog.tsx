// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Search, X, Link2, Check, UserPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Permission = "view" | "edit" | "owner";

interface ShareUser {
  id: string;
  email: string;
  display_name?: string;
  permission: Permission;
}

interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  resourceType: "workflow" | "conversation" | "knowledge" | "agent";
  resourceName: string;
  resourceId: string;
  existingShares?: ShareUser[];
  onShare?: (users: ShareUser[]) => void;
}

const permissionConfig: Record<Permission, { label: string; color: string }> = {
  view: { label: "View", color: "bg-muted text-muted-foreground" },
  edit: { label: "Edit", color: "bg-primary/10 text-primary" },
  owner: { label: "Owner", color: "bg-amber-500/10 text-amber-600" },
};

const mockSearchResults = [
  { id: "user-1", email: "alice@example.com", display_name: "Alice Johnson" },
  { id: "user-2", email: "bob@example.com", display_name: "Bob Smith" },
  { id: "user-3", email: "carol@example.com", display_name: "Carol Williams" },
];

const ShareDialog = ({
  open,
  onOpenChange,
  resourceType,
  resourceName,
  resourceId,
  existingShares = [],
  onShare,
}: ShareDialogProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [shares, setShares] = useState<ShareUser[]>(existingShares);
  const [selectedPermission, setSelectedPermission] = useState<Permission>("view");
  const [linkCopied, setLinkCopied] = useState(false);

  const filteredResults = searchQuery.trim()
    ? mockSearchResults.filter(
        (u) =>
          (u.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
            u.display_name?.toLowerCase().includes(searchQuery.toLowerCase())) &&
          !shares.some((s) => s.id === u.id)
      )
    : [];

  const handleAddUser = (user: typeof mockSearchResults[0]) => {
    const newShare: ShareUser = {
      id: user.id,
      email: user.email,
      display_name: user.display_name,
      permission: selectedPermission,
    };
    setShares([...shares, newShare]);
    setSearchQuery("");
  };

  const handleRemoveUser = (userId: string) => {
    setShares(shares.filter((s) => s.id !== userId));
  };

  const handlePermissionChange = (userId: string, permission: Permission) => {
    setShares(
      shares.map((s) => (s.id === userId ? { ...s, permission } : s))
    );
  };

  const handleCopyLink = async () => {
    const shareUrl = `${window.location.origin}/share/${resourceType}/${resourceId}`;
    await navigator.clipboard.writeText(shareUrl);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
    toast.success("Link copied to clipboard");
  };

  const handleSave = () => {
    onShare?.(shares);
    toast.success(`${resourceType} shared successfully`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share {resourceType}</DialogTitle>
          <DialogDescription>
            Share "{resourceName}" with others
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Search input */}
          <div className="space-y-2">
            <Label>Add people</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by email or name..."
                  className="pl-9"
                />
              </div>
              <Select
                value={selectedPermission}
                onValueChange={(v) => setSelectedPermission(v as Permission)}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">View</SelectItem>
                  <SelectItem value="edit">Edit</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Search results dropdown */}
            {filteredResults.length > 0 && (
              <div className="border border-border rounded-lg overflow-hidden">
                {filteredResults.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => handleAddUser(user)}
                    className="w-full flex items-center gap-3 px-3 py-2 hover:bg-muted transition-colors text-left"
                  >
                    <Avatar className="w-8 h-8">
                      <AvatarFallback className="text-xs">
                        {user.display_name?.charAt(0) || user.email.charAt(0)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {user.display_name || user.email}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {user.email}
                      </p>
                    </div>
                    <UserPlus className="w-4 h-4 text-muted-foreground" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Shared users list */}
          {shares.length > 0 && (
            <div className="space-y-2">
              <Label>People with access</Label>
              <ScrollArea className="max-h-40">
                <div className="space-y-2">
                  {shares.map((user) => (
                    <div
                      key={user.id}
                      className="flex items-center gap-3 p-2 rounded-lg bg-muted/30"
                    >
                      <Avatar className="w-8 h-8">
                        <AvatarFallback className="text-xs">
                          {user.display_name?.charAt(0) || user.email.charAt(0)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {user.display_name || user.email}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {user.email}
                        </p>
                      </div>
                      <Select
                        value={user.permission}
                        onValueChange={(v) =>
                          handlePermissionChange(user.id, v as Permission)
                        }
                        disabled={user.permission === "owner"}
                      >
                        <SelectTrigger className="w-20 h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="view">View</SelectItem>
                          <SelectItem value="edit">Edit</SelectItem>
                        </SelectContent>
                      </Select>
                      {user.permission !== "owner" && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="w-8 h-8"
                          onClick={() => handleRemoveUser(user.id)}
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}

          {/* Copy link */}
          <div className="pt-2 border-t border-border">
            <Button
              variant="outline"
              className="w-full"
              onClick={handleCopyLink}
            >
              {linkCopied ? (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Copied!
                </>
              ) : (
                <>
                  <Link2 className="w-4 h-4 mr-2" />
                  Copy link
                </>
              )}
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ShareDialog;
