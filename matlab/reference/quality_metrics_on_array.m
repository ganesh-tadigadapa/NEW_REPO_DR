function quality_metrics_on_array(matIn, jsonOut)
% QUALITY_METRICS_ON_ARRAY  Compute the quality metrics on PRE-SUPPLIED arrays.
%
% Isolates metric fidelity from preprocessing. The caller (compare_matlab_python.py)
% hands over the exact grayscale array and retina mask that the Python implementation
% used, so any remaining difference is attributable to the metric code alone, not to
% resampling or morphology differences between OpenCV and MATLAB.
%
% This is the number that answers "is the algorithm correctly ported?".
% The end-to-end comparison answers a different question: "do two independent
% preprocessing stacks produce identical pixels?" -- and they do not, which is expected.

d = load(matIn);
R = d.rows;
if iscell(R), getr = @(i) R{i}; else, getr = @(i) R(i); end
n = numel(R);
out = cell(n,1);
for i = 1:n
    r = getr(i);
    G = double(r.gray);
    M = logical(r.mask);

    % focus: contrast-normalised Tenengrad, OpenCV Sobel kernel, BORDER_REFLECT_101
    kx = [-1 0 1; -2 0 2; -1 0 1]; ky = kx';
    P = [G(2,:); G; G(end-1,:)];
    P = [P(:,2), P, P(:,end-1)];
    gx = conv2(P, kx, 'valid'); gy = conv2(P, ky, 'valid');
    focus = mean(gx(M).^2 + gy(M).^2) / var(G(M), 1) * 100;

    % illumination: 3x3 grid coefficient of variation
    [h, w] = size(G); means = [];
    for a = 0:2
        for b = 0:2
            ys = floor(a*h/3)+1; ye = floor((a+1)*h/3);
            xs = floor(b*w/3)+1; xe = floor((b+1)*w/3);
            cm = M(ys:ye, xs:xe);
            if mean(cm(:)) < 0.35, continue; end
            cc = G(ys:ye, xs:xe);
            means(end+1) = mean(cc(cm)); %#ok<AGROW>
        end
    end
    if numel(means) < 2 || mean(means) < 1e-6
        illum = 1.0;
    else
        illum = std(means, 1) / mean(means);
    end

    out{i} = struct('idx', i, 'focus_tenengrad_norm', focus, ...
                    'illumination_grid_cv', illum);
end
payload = [out{:}];
fid = fopen(jsonOut,'w'); fprintf(fid,'%s',jsonencode(payload,'PrettyPrint',true)); fclose(fid);
fprintf('wrote %s\n', jsonOut);
end
