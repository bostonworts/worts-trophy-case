class ApplicationController < ActionController::Base
  include Passwordless::ControllerHelpers

  helper_method :current_user

  private

  def current_user
    @current_user ||= authenticate_by_cookie(User)
  end

  def require_user!
    if current_user
      if current_user.deactivated?
        redirect_to root_path, flash: {
          error: "It looks like #{current_user.email} is no longer a Boston Worts member. Extend your membership so you can post your trophies!"
        }
      end
    else
      save_passwordless_redirect_location!(User)
      redirect_to users.sign_in_path, flash: {
        error: "Hi! You must log in as a Boston Worts member to do this."
      }
    end
  end
end
