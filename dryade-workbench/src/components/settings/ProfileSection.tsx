// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Palette, User, Mail, Calendar, Clock, Shield, Check, Copy } from "lucide-react";
import { SettingsCard, SettingRow } from "./SettingsCard";
import { useAuth } from "@/contexts/AuthContext";
import { usersApi } from "@/services/api";
import { toast } from "sonner";
import type { User as UserType } from "@/types/extended-api";

const avatarColors = [
  "#2BAB38", "#4FD45C", "#7CDE83", "#144330",
  "#6DBB8E", "#0E3A2B", "#9DD4B3", "#0369A1",
];

interface ProfileSectionProps {
  user: UserType;
}

export const ProfileSection = ({ user }: ProfileSectionProps) => {
  const { user: authUser, refreshUser } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ display_name: user.display_name || "" });
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [copied, setCopied] = useState(false);

  const getInitials = (name?: string | null) => {
    if (!name) return "??";
    return name.split(" ").filter(Boolean).map((n) => n[0]).join("").toUpperCase().slice(0, 2) || "??";
  };

  const handleSaveProfile = async () => {
    if (!authUser) return;
    try {
      await usersApi.updateCurrentUser({ display_name: editForm.display_name, preferences: { ...(authUser.preferences || {}), avatar_color: user.avatar_color } });
      await refreshUser();
      setIsEditing(false);
      toast.success("Profile updated successfully");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update profile");
    }
  };

  const handleColorChange = async (color: string) => {
    if (!authUser) return;
    setShowColorPicker(false);
    try {
      await usersApi.updateCurrentUser({ preferences: { ...(authUser.preferences || {}), avatar_color: color } });
      await refreshUser();
      toast.success("Avatar color updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update avatar color");
    }
  };

  const handleCopyId = async () => {
    await navigator.clipboard.writeText(user.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("User ID copied to clipboard");
  };

  return (
    <div className="space-y-4">
      <SettingsCard>
        <div className="flex items-center gap-4 py-2">
          <div className="relative group shrink-0">
            <Avatar className="w-16 h-16 text-lg">
              <AvatarFallback style={{ backgroundColor: user.avatar_color }} className="text-white">
                {getInitials(user.display_name || user.email)}
              </AvatarFallback>
            </Avatar>
            <Dialog open={showColorPicker} onOpenChange={setShowColorPicker}>
              <DialogTrigger asChild>
                <button className="absolute inset-0 flex items-center justify-center bg-background/60 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
                  <Palette className="w-4 h-4 text-foreground" />
                </button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[280px]">
                <DialogHeader><DialogTitle>Choose Avatar Color</DialogTitle></DialogHeader>
                <div className="grid grid-cols-4 gap-3 py-4">
                  {avatarColors.map((color) => (
                    <button key={color} onClick={() => handleColorChange(color)}
                      className={cn("w-10 h-10 rounded-full transition-transform hover:scale-110", user.avatar_color === color && "ring-2 ring-offset-2 ring-primary")}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </DialogContent>
            </Dialog>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-foreground truncate">{user.display_name || "No name set"}</h3>
            <p className="text-sm text-muted-foreground truncate">{user.email}</p>
            <div className="flex items-center gap-2 mt-1.5">
              <Badge variant={user.role === "admin" ? "default" : "secondary"}
                className={cn(user.role === "admin" && "bg-warning/10 text-warning border-warning/30")}>
                <Shield className="w-3 h-3 mr-1" />
                {user.role === "admin" ? "Admin" : "Member"}
              </Badge>
              {user.is_external && <Badge variant="outline">SSO</Badge>}
            </div>
          </div>
          {!isEditing && (
            <Button variant="outline" size="sm" onClick={() => setIsEditing(true)} className="shrink-0">Edit</Button>
          )}
        </div>
      </SettingsCard>

      {isEditing ? (
        <SettingsCard title="Edit Profile">
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="display_name">Display Name</Label>
              <Input id="display_name" value={editForm.display_name} onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })} placeholder="Enter your name" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={user.email} disabled className="bg-muted" />
              <p className="text-xs text-muted-foreground">Email cannot be changed.</p>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSaveProfile}>Save</Button>
              <Button variant="outline" onClick={() => setIsEditing(false)}>Cancel</Button>
            </div>
          </div>
        </SettingsCard>
      ) : (
        <SettingsCard title="Details">
          <SettingRow label="Display Name" description={user.display_name || "Not set"}>
            <User className="w-4 h-4 text-muted-foreground" />
          </SettingRow>
          <SettingRow label="Email" description={user.email}>
            <Mail className="w-4 h-4 text-muted-foreground" />
          </SettingRow>
          <SettingRow label="Member Since" description={new Date(user.first_seen).toLocaleDateString()}>
            <Calendar className="w-4 h-4 text-muted-foreground" />
          </SettingRow>
          <SettingRow label="Last Active" description={new Date(user.last_seen).toLocaleDateString()}>
            <Clock className="w-4 h-4 text-muted-foreground" />
          </SettingRow>
          <SettingRow label="User ID" description={user.id}>
            <Button variant="ghost" size="icon" onClick={handleCopyId} className="h-8 w-8">
              {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
            </Button>
          </SettingRow>
        </SettingsCard>
      )}
    </div>
  );
};
