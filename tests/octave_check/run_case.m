function run_case(w,l,n,ti,ts,g,mu,type_,esl,ndd,nrd,perc1,perc2,msf,dl,dr,dd1,dd2)
  addpath('../../reference');
  [a,b,c,d,e,f,gg,h,ii,jj,kk] = des_reinf_bearing_bsi_test_2(w,l,n,ti,ts,g,mu,type_,esl,ndd,nrd,perc1,perc2,msf,dl,dr,dd1,dd2);
  printf('max_ver_def_alwd=%.10g\n', a);
  printf('max_vec_shear_def=%.10g\n', b);
  printf('disp_upperbound=%.10g\n', c);
  printf('max_load=%.10g\n', d);
  printf('min_load=%.10g\n', e);
  printf('load_upperbound=%.10g\n', f);
  printf('max_ang_w=%.10g\n', gg);
  printf('rot_upperbound=%.10g\n', h);
  printf('Max_force_exerted=%.10g\n', ii);
  printf('Max_moment=%.10g\n', jj);
  printf('overal_height=%.10g\n', kk);
end
