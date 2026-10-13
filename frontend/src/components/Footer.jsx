import "./Footer.css";

const CURRENT_YEAR = new Date().getFullYear();

/**
 * The plain footer under every screen's <Outlet>, matching the
 * Administration mockup's own footer: two small lines of text on the
 * page's own light background with a thin top border, not a second
 * branded color block. (This page's mockup is the first of the
 * reference screenshots to actually show a footer; the heavier,
 * accent-filled footer this component had before was a guess made
 * without seeing it.)
 */
export default function Footer() {
  return (
    <footer className="app-footer">
      <span>Strathmore University, BSc Informatics and Computer Science capstone project</span>
      <span>&copy; {CURRENT_YEAR} Daniella Wambua. All rights reserved.</span>
    </footer>
  );
}
