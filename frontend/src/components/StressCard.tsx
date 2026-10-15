import { get } from "../api/client";
import type { StressTest } from "../api/types";
import { useAsync } from "../hooks";
import { ErrorNotice, Loading } from "./Ui";

interface Props {
  quoteId: string;
  providerId: string;
}

/** Currency-drop stress test: the chosen quote priced again if the taka weakens. The engine does the maths. */
export function StressCard({ quoteId, providerId }: Props) {
  const stress = useAsync(
    () => get<StressTest>(`/quotes/${quoteId}/stress?provider_id=${encodeURIComponent(providerId)}`),
    [quoteId, providerId],
  );
  const data = stress.data;
  return (
    <section className="card" aria-labelledby="stress-title">
      <h2 id="stress-title">Currency-drop stress test</h2>
      <p className="small muted">
        What if the taka weakens before you send? Same provider, same fees, with each {data?.target.currency ?? "foreign unit"} costing more taka.
      </p>
      <ErrorNotice error={stress.error} />
      {stress.loading && !data ? <Loading what="Pricing the what-if" /> : null}
      {data ? (
        <>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Currency-drop stress test table">
            <table>
              <caption className="sr-only">
                {data.provider_name}: what you would pay if the taka weakens
              </caption>
              <thead>
                <tr>
                  <th scope="col">If each {data.target.currency} costs</th>
                  <th scope="col" className="num">Rate (BDT per {data.target.currency})</th>
                  <th scope="col" className="num">You would pay</th>
                  <th scope="col" className="num">Extra</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Today</th>
                  <td className="num">{data.baseline.display.provider_rate}</td>
                  <td className="num">{data.baseline.display.parent_pays}</td>
                  <td className="num muted">None</td>
                </tr>
                {data.scenarios.map((row) => (
                  <tr key={row.drop_pct}>
                    <th scope="row">{row.drop_pct} more taka</th>
                    <td className="num">{row.display.provider_rate}</td>
                    <td className="num">{row.display.parent_pays}</td>
                    <td className="num error-text">
                      {row.display.extra} ({row.display.extra_pct})
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            {data.assumption} {data.note}
          </p>
        </>
      ) : null}
    </section>
  );
}
