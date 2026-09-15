function results = run_sweeps()
% RUN_SWEEPS  The economic argument, in one chart.
%
% Sweeps the number of ophthalmologists with and without AI triage and finds the minimum
% staffing at which the review queue is stable (mean wait bounded) and the annual
% caseload is actually cleared.
%
% Output: matlab/simulink/sweep_results.json + a figure. The single number this produces
% — "N ophthalmologists with AI versus M without" — is the slide that makes a panel sit
% up, so it must come from a real run, not from arithmetic on a napkin.

here = fileparts(mfilename('fullpath'));
staffing = 1:12;
results = struct('withAI', [], 'withoutAI', [], 'staffing', staffing);

for aiEnabled = [true false]
    rows = [];
    for n = staffing
        mdl = build_dr_workflow_model( ...
            'nOphthalmologists', n, 'aiEnabled', aiEnabled);
        simOut = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
        s = collect_stats(simOut);
        s.nOphthalmologists = n;
        s.aiEnabled = aiEnabled;
        rows = [rows; s]; %#ok<AGROW>
        close_system(mdl, 0);
    end
    if aiEnabled, results.withAI = rows; else, results.withoutAI = rows; end
end

results.minStaffWithAI    = min_stable_staffing(results.withAI);
results.minStaffWithoutAI = min_stable_staffing(results.withoutAI);
results.fteSaved = results.minStaffWithoutAI - results.minStaffWithAI;

fid = fopen(fullfile(here, 'sweep_results.json'), 'w');
fwrite(fid, jsonencode(results, 'PrettyPrint', true)); fclose(fid);

fprintf(['\nMinimum ophthalmologists to clear 100,000 patients/year:\n' ...
         '  without AI triage : %d\n  with AI triage    : %d\n  FTEs saved        : %d\n'], ...
    results.minStaffWithoutAI, results.minStaffWithAI, results.fteSaved);

plot_results(results, here);
end

function s = collect_stats(simOut)
% Pull queue wait and utilisation out of the logged SimEvents statistics.
s = struct('meanWaitHours', NaN, 'utilisation', NaN, 'throughput', NaN);
try
    logsout = simOut.get('logsout');
    s.meanWaitHours = mean(logsout.get('Review Queue').Values.Data) / 3600;
    s.utilisation   = mean(logsout.get('Ophthalmologist Review').Values.Data);
catch
    warning('statistics not logged — enable signal logging on the queue and server');
end
end

function n = min_stable_staffing(rows)
% "Stable" = mean queue wait under one working week. A queue that grows without bound
% means the district cannot clear its caseload at that staffing level, whatever the
% instantaneous utilisation looks like.
n = NaN;
for i = 1:numel(rows)
    if rows(i).meanWaitHours < 30 && rows(i).utilisation < 0.85
        n = rows(i).nOphthalmologists; return;
    end
end
end

function plot_results(r, here)
f = figure('Visible', 'off');
plot([r.withoutAI.nOphthalmologists], [r.withoutAI.meanWaitHours], '-o', ...
     [r.withAI.nOphthalmologists],    [r.withAI.meanWaitHours],    '-s', 'LineWidth', 1.6);
legend('Without AI triage', 'With AI triage'); grid on;
xlabel('Ophthalmologist FTEs'); ylabel('Mean review-queue wait (hours)');
title('District screening: 100,000 patients/year');
saveas(f, fullfile(here, 'staffing_sweep.png')); close(f);
end
