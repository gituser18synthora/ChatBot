import { useEffect, useState } from "react";
import { tenantApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { Select } from "@/components/ui/Field";
import type { Tenant } from "@/api/types";

/**
 * Resolves the tenant a page should operate on.
 * - Super Admin: a selectable dropdown (loaded from the API).
 * - Tenant Admin / Chat User: locked to their own tenant.
 *
 * `allowAll` adds an "All tenants" option (for analytics/audit list views).
 */
export function useTenantScope(allowAll = false) {
  const { user, isSuperAdmin } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState<string | "">(allowAll ? "" : user?.tenant_id || "");
  const [loading, setLoading] = useState(isSuperAdmin);

  useEffect(() => {
    if (!isSuperAdmin) {
      setSelected(user?.tenant_id || "");
      return;
    }
    let active = true;
    setLoading(true);
    tenantApi
      .list({ per_page: 100 })
      .then((res) => {
        if (!active) return;
        setTenants(res.items);
        if (!allowAll && !selected && res.items.length) setSelected(res.items[0].id);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuperAdmin]);

  return { isSuperAdmin, tenants, selected, setSelected, loading };
}

export function TenantPicker({
  tenants,
  value,
  onChange,
  allowAll,
  className,
}: {
  tenants: Tenant[];
  value: string;
  onChange: (v: string) => void;
  allowAll?: boolean;
  className?: string;
}) {
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} className={className}>
      {allowAll && <option value="">All tenants</option>}
      {tenants.map((t) => (
        <option key={t.id} value={t.id}>
          {t.tenant_name}
        </option>
      ))}
    </Select>
  );
}
