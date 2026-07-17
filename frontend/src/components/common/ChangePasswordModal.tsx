import { FormEvent, useState } from "react";
import { profileApi } from "@/api/services";
import { useToast } from "@/context/ToastContext";
import { Modal } from "@/components/ui/Modal";
import { Field, TextInput } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/primitives";
import InputField from "./InputField";

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
          <InputField
            name="password"
            type="password"
            value={form.current}
            required
            placeholder="Enter password"
            onChange={(name, value) => setForm({ ...form, current: value })}
          />
        </Field>
        <Field label="New password" required hint="At least 8 characters.">
          <InputField
            name="password"
            type="password"
            value={form.next}
            required
            placeholder="Enter password"
            onChange={(name, value) => setForm({ ...form, next: value })}
          />
        </Field>
        <Field label="Confirm new password" required>
          <InputField
            name="password"
            type="password"
            value={form.confirm}
            required
            placeholder="Enter password"
            onChange={(name, value) => setForm({ ...form, confirm: value })}
          />
        </Field>
      </form>
    </Modal>
  );
}
