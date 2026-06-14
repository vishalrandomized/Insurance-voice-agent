import styles from "../../components/sales/sales-dashboard.module.css";

export default function SalesLoading() {
  return (
    <main className={styles.loadingShell} aria-label="Loading sales console">
      <div className={styles.loadingMark}>AP</div>
      <div className={styles.loadingLine} />
      <p>Opening advisor console</p>
    </main>
  );
}
