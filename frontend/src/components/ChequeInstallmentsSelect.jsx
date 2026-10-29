import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { CHEQUE_INSTALLMENTS } from "@/lib/saleConstants";

export const ChequeInstallmentsSelect = ({ value, onChange, testid }) => {
  const n = parseInt(value || 1, 10);
  const [custom, setCustom] = useState(!CHEQUE_INSTALLMENTS.includes(n));
  const selectValue = custom ? "custom" : String(n);
  return (
    <div className="flex gap-2">
      <Select value={selectValue} onValueChange={(v) => {
        if (v === "custom") { setCustom(true); return; }
        setCustom(false); onChange(parseInt(v, 10));
      }}>
        <SelectTrigger data-testid={testid} className="flex-1"><SelectValue /></SelectTrigger>
        <SelectContent>
          {CHEQUE_INSTALLMENTS.map((k) => (<SelectItem key={k} value={String(k)}>{k === 1 ? "En 1 fois" : `${k} fois`}</SelectItem>))}
          <SelectItem value="custom" data-testid={`${testid}-custom-option`}>Autre (préciser)</SelectItem>
        </SelectContent>
      </Select>
      {custom && (
        <Input type="number" min={1} max={60} className="w-24" data-testid={`${testid}-custom-input`}
          value={value || ""} placeholder="Nb"
          onChange={(e) => onChange(e.target.value === "" ? "" : Math.max(1, parseInt(e.target.value, 10) || 1))} />
      )}
    </div>
  );
};
