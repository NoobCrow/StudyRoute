import type { SendPlan } from "../api/types";
import { Badge } from "./Ui";

/** The smart send plan: the same money sent monthly, quarterly, per term or all at once. */
export function SendPlanTable({ plan, compact = false }: { plan: SendPlan; compact?: boolean }) {
  return (
    <div>
      <p className="small muted">
        {plan.total.formatted} over {plan.months} months. Totals are the true cost in BDT, from the engine.
      </p>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Send plan comparison table">
        <table>
          <caption className="sr-only">True total cost of each way of sending the money</caption>
          <thead>
            <tr>
              <th scope="col">Way of sending</th>
              <th scope="col" className="num">Transfers</th>
              {compact ? null : <th scope="col">Cheapest provider</th>}
              <th scope="col" className="num">Total cost</th>
              <th scope="col" className="num">Saves</th>
            </tr>
          </thead>
          <tbody>
            {plan.options.map((o) => (
              <tr key={o.key} className={o.key === plan.cheapest_key ? "best" : undefined}>
                <td>
                  <strong>{o.label}</strong>
                  <div className="small muted">{o.display.per_transfer} each</div>
                  {o.key === plan.cheapest_key ? <Badge tone="ok">Cheapest on paper</Badge> : null}
                  {o.exceeds_sandbox_cap ? <Badge tone="warn">Over the sandbox cap</Badge> : null}
                </td>
                <td className="num">{o.transfers}</td>
                {compact ? null : <td>{o.provider_name}</td>}
                <td className="num">{o.display.total_cost}</td>
                <td className="num">{o.key === "monthly" ? "-" : o.display.saving_vs_monthly}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small">{plan.trade_off}</p>
      <p className="small muted">{plan.disclaimer}</p>
    </div>
  );
}
