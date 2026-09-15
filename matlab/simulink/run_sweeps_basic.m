function results = run_sweeps_basic(opts)
% RUN_SWEEPS_BASIC  Staffing sweep on the base-Simulink workflow model.
%
% Answers the economic question: how many ophthalmologist FTEs does a district of
% 100,000 diabetics need, WITH and WITHOUT AI triage in front of them?
%
% Method: for each staffing level, build the model, simulate one working year, and read
% the final backlog. A district is VIABLE at that staffing level if the backlog stays
% bounded (does not grow all year). The minimum viable FTE is the answer.
%
%   results = run_sweeps_basic();
%
% Writes ../../results/simulation/simulink_sweep.json so the number in the deck traces
% to a file, per CLAUDE.md rule 2.

arguments
    opts.maxDocs         (1,1) double = 8
    opts.patientsPerYear (1,1) double = 100000
end

fprintf('\n=== DR district staffing sweep (base Simulink) ===\n');

modes   = [true false];
modeName = ["with_ai" "without_ai"];
results = struct();

for m = 1:2
    ai = modes(m);
    fprintf('\n--- AI %s ---\n', string(ai));
    backlogs = nan(1, opts.maxDocs);
    viable   = NaN;

    for n = 1:opts.maxDocs
        [mdl, cfg] = build_dr_workflow_basic(nOphthalmologists=n, aiEnabled=ai, ...
                                      patientsPerYear=opts.patientsPerYear);
        lastCfg = cfg;
        simOut = sim(mdl);
        bl = simOut.backlog.Data;
        finalBacklog = bl(end);
        backlogs(n) = finalBacklog;

        % Bounded means the backlog is not still climbing at year end.
        isStable = finalBacklog < 1.0;
        if isStable, verdict = 'STABLE'; else, verdict = 'GROWING'; end
        fprintf('  %d doc(s): final backlog %10.1f  %s\n', n, finalBacklog, verdict);
        if isStable && isnan(viable); viable = n; end
        close_system(mdl, 0);
        clear(mdl);
    end

    results.(modeName(m)) = struct('final_backlog', backlogs, ...
                                   'min_ophthalmologists', viable);
end

withAI    = results.with_ai.min_ophthalmologists;
withoutAI = results.without_ai.min_ophthalmologists;
fteSaved  = withoutAI - withAI;

fprintf('\n=== RESULT ===\n');
fprintf('  Minimum ophthalmologists WITH AI triage:    %d\n', withAI);
fprintf('  Minimum ophthalmologists WITHOUT AI triage: %d\n', withoutAI);
fprintf('  FTEs saved per 100k diabetics:              %d\n', fteSaved);

% ---- write the evidence file ------------------------------------------------
here   = fileparts(mfilename('fullpath'));
outDir = fullfile(here, '..', '..', 'results', 'simulation');
if ~isfolder(outDir); mkdir(outDir); end

payload = struct( ...
    'generated_at',              string(datetime('now','TimeZone','UTC','Format','uuuu-MM-dd''T''HH:mm:ss''Z''')), ...
    'implementation',            'MATLAB base Simulink discrete-time flow model (matlab/simulink/build_dr_workflow_basic.m)', ...
    'note',                      ['SimEvents is not available on this licence, so the graded ' ...
                                  'deliverable is a discrete-TIME flow approximation rather than ' ...
                                  'a discrete-EVENT model. Cross-check against the independent ' ...
                                  'Python SimPy implementation in scripts/simulate_workflow.py.'], ...
    'patients_per_year',         opts.patientsPerYear, ...
    'min_ophthalmologists_with_ai',    withAI, ...
    'min_ophthalmologists_without_ai', withoutAI, ...
    'fte_saved',                 fteSaved, ...
    'parameters_are_measured',   isempty(lastCfg.params.unmeasured_fields), ...
    'unmeasured_parameters',     {lastCfg.params.unmeasured_fields}, ...
    'parameters_used',           lastCfg.params, ...
    'honesty_note',              ['Any parameter listed in unmeasured_parameters fell ' ...
                                  'back to a documented placeholder. referableRate and ' ...
                                  'disagreementRate require a real dataset evaluation ' ...
                                  '(not demo traffic), so the FTE figure is ' ...
                                  'placeholder-influenced until the holdout has run.'], ...
    'final_backlog_with_ai',     results.with_ai.final_backlog, ...
    'final_backlog_without_ai',  results.without_ai.final_backlog);

fid = fopen(fullfile(outDir, 'simulink_sweep.json'), 'w');
fprintf(fid, '%s', jsonencode(payload, 'PrettyPrint', true));
fclose(fid);
fprintf('\nWrote results/simulation/simulink_sweep.json\n');
end
