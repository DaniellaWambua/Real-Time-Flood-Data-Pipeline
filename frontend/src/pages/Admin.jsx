import { useOutletContext, useSearchParams } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import OverviewTab from "./admin/OverviewTab";
import UsersTab from "./admin/UsersTab";
import ActivityTab from "./admin/ActivityTab";
import "./Admin.css";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users" },
  { id: "activity", label: "Activity log" },
];

// System administration, split into tabs that each do one job. The open tab is kept in
// the address (?tab=users), so it survives a refresh and can be linked to.
export default function Admin() {
  const { user } = useOutletContext();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.id === params.get("tab")) ? params.get("tab") : "overview";

  // A second gate behind the hidden nav link, matching the server's own role check
  if (user.role !== "system_administrator") {
    return <EmptyState>System administration is restricted to the System Administrator role.</EmptyState>;
  }

  return (
    <section>
      <PageHeader title="Administration" subtitle="System health, user access and activity" />

      <div className="admin-tabs" role="tablist" aria-label="Administration sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setParams({ tab: t.id })}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab currentUserId={user.id} />}
      {tab === "activity" && <ActivityTab />}
    </section>
  );
}
