module math_utils
  implicit none

contains

  real function square(x)
    real, intent(in) :: x

    square = x * x
  end function square


  subroutine print_square(x)
    real, intent(in) :: x

    print *, "square =", square(x)
  end subroutine print_square

end module math_utils


module simulation
  use math_utils, only: print_square
  implicit none

contains

  subroutine run_simulation(value)
    real, intent(in) :: value

    call print_square(value)
  end subroutine run_simulation

end module simulation


program main
  use simulation, only: run_simulation
  implicit none

  call run_simulation(3.0)
end program main
