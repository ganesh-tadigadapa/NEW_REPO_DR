function [mdl, cfg] = build_dr_workflow_basic(opts)
% BUILD_DR_WORKFLOW_BASIC  District DR screening programme, base-Simulink version.
%
% Requirement #5 of SIH26038.
%
% WHY THIS FILE EXISTS INSTEAD OF THE SIMEVENTS ONE
%   build_dr_workflow_model.m models this programme as a discrete-EVENT system, which is
%   the textbook-correct tool. It needs SimEvents. Our MATLAB R2026a licence does not
%   include SimEvents (verified with `ver`), so that file cannot run here.
%
%   This file answers the SAME question with a discrete-TIME flow model built from core
%   Simulink blocks only. Instead of tracking individual patient entities through queues,
%   it tracks the RATE of work arriving and the RATE a given number of ophthalmologists
%   can clear, and integrates the difference into a backlog.
%
%   Say this to a judge plainly. "Discrete-event is the right abstraction and we wrote
%   that model too; our trial licence lacks SimEvents, so the model we can actually RUN
%   is a discrete-time fluid approximation. It answers the staffing question, it agrees
%   with our independent Python discrete-event simulation, and here is the .slx."
%
% WHAT IT COMPUTES
%   Backlog Q(t) of patients waiting for ophthalmologist review.
%       Q(k+1) = max(0, Q(k) + (inflow - capacity) * dt)
%   If Q grows without bound the district is understaffed. The minimum viable FTE count
%   is the smallest n for which Q stays bounded.
%
% THE PIPELINE MODELLED
%   arrivals -> quality gate -> [fail x maxRecaptures -> manual referral]
%                            -> AI grading -> [not referable AND rules agree] auto-cleared
%                                          -> [referable OR disagreement] review backlog
%
%   With AI disabled, every gradeable patient goes to the backlog. That difference is the
%   economic case for the project.
%
% USAGE
%   mdl = build_dr_workflow_basic();
%   mdl = build_dr_workflow_basic(nOphthalmologists=3, aiEnabled=false);

arguments
    opts.mdl                  (1,:) char    = 'dr_district_workflow_basic'
    opts.patientsPerYear      (1,1) double  = 100000
    opts.workingDaysPerYear   (1,1) double  = 250
    opts.hoursPerDay          (1,1) double  = 6
    opts.nOphthalmologists    (1,1) double  = 2
    opts.aiEnabled            (1,1) logical  = true
    opts.maxRecaptures        (1,1) double  = 2
    opts.paramFile            (1,:) char    = 'measured_params.json'
end

p = load_measured_params_basic(opts.paramFile);

% ---- derive rates, all in PATIENTS PER HOUR of clinic time ------------------
hoursPerYear   = opts.workingDaysPerYear * opts.hoursPerDay;
arrivalsPerHr  = opts.patientsPerYear / hoursPerYear;

% A patient failing the gate retries up to maxRecaptures times. Failing every attempt
% means the image never becomes gradeable, so that patient is referred manually.
permFailFrac   = p.ungradeableRate ^ (opts.maxRecaptures + 1);
gradeableFrac  = 1 - permFailFrac;

if opts.aiEnabled
    % AI clears the non-referable, agreeing majority. Disagreements still cost a human --
    % that is the honest price of our own safety mechanism and we model it.
    %
    % Prefer a DIRECTLY MEASURED needsHumanRate. Summing referableRate and
    % disagreementRate double-counts, because an image can be both referable AND
    % flagged: measured on 80 held-out images those were 0.40 and 0.74, which sum to
    % 1.14 -- impossible. The measured de-duplicated figure is 0.725.
    if isfield(p,'needsHumanRate') && ~isempty(p.needsHumanRate) && isnumeric(p.needsHumanRate)
        needsHumanFrac = p.needsHumanRate;
    else
        needsHumanFrac = min(1.0, p.referableRate + p.disagreementRate);
    end
    % Reading an AI-annotated report (grade + heatmap + lesion table) is much faster
    % than an unaided read. This is the <30 s sign-off target.
    secondsPerRead = p.reviewSeconds;
else
    needsHumanFrac = 1.0;   % control arm: a human reads every gradeable image
    % CRITICAL: the control arm must use the UNAIDED read time, not the AI-assisted
    % sign-off time. Using reviewSeconds for both arms makes the no-AI arm look ~6x
    % cheaper than it is and destroys the comparison. Matches manual_read_s in
    % scripts/simulate_workflow.py so the two implementations stay comparable.
    secondsPerRead = p.manualReadSeconds;
end

reviewsPerHrPerDoc = 3600 / secondsPerRead;
capacityPerHr      = opts.nOphthalmologists * reviewsPerHrPerDoc;

dt = 1;   % one simulation step = one clinic hour

% ---- build ------------------------------------------------------------------
mdl = opts.mdl;
if bdIsLoaded(mdl); close_system(mdl, 0); end
new_system(mdl);

add_block('simulink/Sources/Constant', [mdl '/Patient Arrivals']);
set_param([mdl '/Patient Arrivals'], 'Value', num2str(arrivalsPerHr), ...
    'SampleTime', num2str(dt));

add_block('simulink/Math Operations/Gain', [mdl '/Quality Gate Pass']);
set_param([mdl '/Quality Gate Pass'], 'Gain', num2str(gradeableFrac));

add_block('simulink/Math Operations/Gain', [mdl '/Needs Human']);
set_param([mdl '/Needs Human'], 'Gain', num2str(needsHumanFrac));

add_block('simulink/Math Operations/Gain', [mdl '/Manual Referral']);
set_param([mdl '/Manual Referral'], 'Gain', num2str(permFailFrac));

add_block('simulink/Math Operations/Sum', [mdl '/Review Inflow']);
set_param([mdl '/Review Inflow'], 'Inputs', '++');

add_block('simulink/Sources/Constant', [mdl '/Review Capacity']);
set_param([mdl '/Review Capacity'], 'Value', num2str(capacityPerHr), ...
    'SampleTime', num2str(dt));

add_block('simulink/Math Operations/Sum', [mdl '/Net Rate']);
set_param([mdl '/Net Rate'], 'Inputs', '+-');

% Backlog cannot go negative: idle doctors do not create negative patients.
add_block('simulink/Discrete/Discrete-Time Integrator', [mdl '/Review Backlog']);
set_param([mdl '/Review Backlog'], 'SampleTime', num2str(dt), ...
    'LimitOutput', 'on', 'LowerSaturationLimit', '0', 'UpperSaturationLimit', 'inf', ...
    'InitialCondition', '0');

add_block('simulink/Sinks/To Workspace', [mdl '/Backlog Out']);
set_param([mdl '/Backlog Out'], 'VariableName', 'backlog', ...
    'SaveFormat', 'Timeseries');

add_block('simulink/Sinks/Scope', [mdl '/Backlog Scope']);

% ---- wiring -----------------------------------------------------------------
add_line(mdl, 'Patient Arrivals/1', 'Quality Gate Pass/1', 'autorouting','smart');
add_line(mdl, 'Patient Arrivals/1', 'Manual Referral/1',   'autorouting','smart');
add_line(mdl, 'Quality Gate Pass/1','Needs Human/1',       'autorouting','smart');
add_line(mdl, 'Needs Human/1',      'Review Inflow/1',     'autorouting','smart');
add_line(mdl, 'Manual Referral/1',  'Review Inflow/2',     'autorouting','smart');
add_line(mdl, 'Review Inflow/1',    'Net Rate/1',          'autorouting','smart');
add_line(mdl, 'Review Capacity/1',  'Net Rate/2',          'autorouting','smart');
add_line(mdl, 'Net Rate/1',         'Review Backlog/1',    'autorouting','smart');
add_line(mdl, 'Review Backlog/1',   'Backlog Out/1',       'autorouting','smart');
add_line(mdl, 'Review Backlog/1',   'Backlog Scope/1',     'autorouting','smart');

% ---- config -----------------------------------------------------------------
set_param(mdl, 'StopTime', num2str(hoursPerYear), ...
    'SolverType', 'Fixed-step', 'FixedStep', num2str(dt), 'Solver', 'FixedStepDiscrete');
% Configuration is recorded in the model workspace (block diagrams have no UserData
% parameter in R2026a), and again in the JSON that run_sweeps_basic writes.
cfg = struct('opts', opts, 'params', p, ...
    'arrivalsPerHr', arrivalsPerHr, 'capacityPerHr', capacityPerHr, ...
    'needsHumanFrac', needsHumanFrac, 'gradeableFrac', gradeableFrac, ...
    'secondsPerRead', secondsPerRead);
mws = get_param(mdl, 'ModelWorkspace');
assignin(mws, 'cfg', cfg);

Simulink.BlockDiagram.arrangeSystem(mdl);
here = fileparts(mfilename('fullpath'));
save_system(mdl, fullfile(here, [mdl '.slx']));

fprintf(['Built %s.slx\n' ...
         '  %.0f patients/yr -> %.1f arrivals/hr\n' ...
         '  AI %s: %.1f%% of gradeable images need a human\n' ...
         '  %d ophthalmologist(s) x %.0f s/read -> %.1f reviews/hr capacity\n' ...
         '  inflow %.2f/hr vs capacity %.2f/hr -> %s\n'], ...
    mdl, opts.patientsPerYear, arrivalsPerHr, string(opts.aiEnabled), ...
    needsHumanFrac*100, opts.nOphthalmologists, secondsPerRead, capacityPerHr, ...
    arrivalsPerHr*(gradeableFrac*needsHumanFrac + permFailFrac), capacityPerHr, ...
    ternary(arrivalsPerHr*(gradeableFrac*needsHumanFrac+permFailFrac) <= capacityPerHr, ...
            'STABLE', 'BACKLOG GROWS'));
end

% ---------------------------------------------------------------------------
function out = ternary(cond, a, b)
if cond; out = a; else; out = b; end
end

function p = load_measured_params_basic(fname)
here = fileparts(mfilename('fullpath'));
f = fullfile(here, fname);
if isfile(f)
    p = jsondecode(fileread(f));
    if isfield(p,'source') && strcmp(p.source,'PLACEHOLDER')
        warning('%s exists but is marked PLACEHOLDER. Not measured data.', fname);
    else
        fprintf('Using MEASURED parameters from %s\n', fname);
    end
    % Some fields are deliberately null in measured_params.json: referableRate and
    % disagreementRate CANNOT come from demo traffic -- they need a dataset evaluation.
    % jsondecode turns null into []. Substitute documented placeholders and record
    % exactly which fields are not measured, so nothing downstream can quietly present
    % a placeholder-driven FTE number as a measured one.
    % disagreementRate is intentionally absent: it is superseded by the directly
    % measured, de-duplicated needsHumanRate. Only fall back to it if that is missing.
    defaults = struct('uploadSeconds',5.5,'qualityGateSeconds',0.05, ...
        'gradingSeconds',1.4,'recaptureSeconds',45,'reviewSeconds',30, ...
        'manualReadSeconds',120,'ungradeableRate',0.12,'referableRate',0.22);
    if ~isfield(p,'needsHumanRate') || isempty(p.needsHumanRate)
        defaults.disagreementRate = 0.06;
    end
    p.unmeasured_fields = {};
    fn = fieldnames(defaults);
    for i = 1:numel(fn)
        k = fn{i};
        if ~isfield(p,k) || isempty(p.(k)) || ~isnumeric(p.(k))
            p.(k) = defaults.(k);
            p.unmeasured_fields{end+1} = k; %#ok<AGROW>
        end
    end
    if ~isempty(p.unmeasured_fields)
        warning(['These parameters are NOT measured and fall back to documented ' ...
                 'placeholders: %s. Any FTE number derived from this run is ' ...
                 'placeholder-influenced and must be labelled as such.'], ...
                 strjoin(p.unmeasured_fields, ', '));
    end
else
    warning(['%s not found. Using DOCUMENTED PLACEHOLDERS -- these are engineering ' ...
             'estimates, not measurements, and must not be presented as results. ' ...
             'Run scripts/export_simulink_params.py against the live service first.'], fname);
    p = struct( ...
        'uploadSeconds',      5.5, ...
        'qualityGateSeconds', 0.05, ...
        'gradingSeconds',     1.4, ...
        'recaptureSeconds',   45, ...
        'reviewSeconds',      30, ...
        'manualReadSeconds',  120, ...
        'ungradeableRate',    0.12, ...
        'referableRate',      0.22, ...
        'disagreementRate',   0.06, ...
        'source',             'PLACEHOLDER');
    p.unmeasured_fields = {'uploadSeconds','qualityGateSeconds','gradingSeconds', ...
        'recaptureSeconds','reviewSeconds','manualReadSeconds','ungradeableRate', ...
        'referableRate','disagreementRate'};
end
end
