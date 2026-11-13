import "./PageHeader.css";

/** The title and subtitle row each screen opens with. */
export default function PageHeader({ title, subtitle }) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        <h1>{title}</h1>
        {subtitle && <p className="page-header-subtitle">{subtitle}</p>}
      </div>
    </div>
  );
}
