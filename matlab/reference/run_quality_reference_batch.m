function run_quality_reference_batch(listFile, outJson)
% RUN_QUALITY_REFERENCE_BATCH  Run the MATLAB quality reference over many images.
%
%   run_quality_reference_batch('paths.txt', 'matlab_quality.json')
%
% listFile: one image path per line. Writes a JSON array of per-image metrics.
% Called by scripts/compare_matlab_python.py, which does the actual comparison.
% One MATLAB startup for the whole batch -- starting MATLAB per image is ~15 s of
% overhead each and would dominate the runtime.

fid = fopen(listFile,'r');
paths = textscan(fid,'%s','Delimiter','\n'); fclose(fid);
paths = paths{1};

n = numel(paths);
out = cell(n,1);
fprintf('MATLAB quality reference over %d images\n', n);
for i = 1:n
    p = strtrim(paths{i});
    if isempty(p), continue; end
    try
        q = retina_quality_reference(p);
        out{i} = struct('image', p, 'ok', true, ...
            'focus_tenengrad_norm', q.focus_tenengrad_norm, ...
            'illumination_grid_cv', q.illumination_grid_cv, ...
            'fov_retina_fraction',  q.fov_retina_fraction, ...
            'fov_centre_offset',    q.fov_centre_offset);
    catch e
        out{i} = struct('image', p, 'ok', false, 'error', e.message, ...
            'focus_tenengrad_norm', NaN, 'illumination_grid_cv', NaN, ...
            'fov_retina_fraction', NaN, 'fov_centre_offset', NaN);
    end
    if mod(i,10)==0, fprintf('  %d/%d\n', i, n); end
end
out = out(~cellfun(@isempty,out));
payload = [out{:}];

fid = fopen(outJson,'w');
fprintf(fid,'%s',jsonencode(payload,'PrettyPrint',true));
fclose(fid);
fprintf('wrote %s\n', outJson);
end
