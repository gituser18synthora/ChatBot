import { FormEvent, useState } from "react";
import { profileApi } from "@/api/services";
import { useToast } from "@/context/ToastContext";
import { Modal } from "@/components/ui/Modal";
import { Field, TextInput } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/primitives";

// Self-service password change, usable from the admin console and the chat UI.
export function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (form.next !== form.confirm) {
      toast.error("The new passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      await profileApi.changePassword(form.current, form.next);
      toast.success("Password updated.");
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Change password"
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" form="password-form" disabled={saving}>
            {saving && <Spinner className="text-white" />}
            Update password
          </button>
        </>
      }
    >
      <form id="password-form" onSubmit={submit} className="space-y-4">
        <Field label="Current password" required>
          <TextInput
            type="password"
            required
            value={form.current}
            onChange={(e) => setForm({ ...form, current: e.target.value })}
          />
        </Field>
        <Field label="New password" required hint="At least 8 characters.">
          <TextInput
            type="password"
            required
            minLength={8}
            value={form.next}
            onChange={(e) => setForm({ ...form, next: e.target.value })}
          />
        </Field>
        <Field label="Confirm new password" required>
          <TextInput
            type="password"
            required
            minLength={8}
            value={form.confirm}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          />
        </Field>
      </form>
    </Modal>
  );
}
