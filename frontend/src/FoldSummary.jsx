// #465 (the #464 mockup): a fold's summary drawn as a list row, as the Django pages draw it
// (records_fold_summary.html, action_icon.html): the pale blue round icon, the title and the
// chevron. Only the icons the React pages fold under.
const ICONS = {
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7.5v.5" />
    </>
  ),
  table: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 10h18M9 10v9" />
    </>
  ),
};

export default function FoldSummary({ icon, title }) {
  return (
    <summary>
      <span className="action-card-icon" aria-hidden="true" data-icon={icon}>
        <svg viewBox="0 0 24 24" focusable="false">{ICONS[icon]}</svg>
      </span>
      <span className="link-card-body">
        <span className="link-card-title">{title}</span>
      </span>
      <span className="result-details-arrow" aria-hidden="true" />
    </summary>
  );
}
